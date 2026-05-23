# train.py

import requests
import time
import threading
import socket
import hashlib
import base64
import numpy as np
from actions import *
from state import *

from ppo import PPO, make_memory

BASE_URL = "http://localhost:8080"
BOT1_NAME = "asd"
BOT2_NAME = "dsa"


def start_game(base_url, p1_name, p2_name):
    r = requests.get(f"{base_url}/game/start/names?player1Name={p1_name}&player2Name={p2_name}", timeout=10)
    r.raise_for_status()
    game_id = r.json()["gameId"]
    print(f"Game started: {game_id}")
    return game_id


def connect_websocket(base_url, game_id):
    """Konektuje se na WebSocket bez eksternih paketa da bi server presao Start -> Player1Turn."""
    parsed = base_url.replace("http://", "")
    host, _, port_str = parsed.partition(":")
    port = int(port_str) if port_str else 80
    path = f"/ws/game?gameId={game_id}"

    key = base64.b64encode(hashlib.md5(game_id.encode()).digest()).decode()
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )

    def run():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.sendall(handshake.encode())
        resp = sock.recv(4096)
        if b"101" in resp:
            print(f"[WS] connected for {game_id}")
        else:
            print(f"[WS] handshake failed: {resp[:200]}")
            return
        while True:
            try:
                if not sock.recv(4096):
                    break
            except Exception:
                break
        sock.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread

ROLLOUT_STEPS = 512
TOTAL_UPDATES = 1000


def reward_fn(prev_state, next_state, done=False):
    reward = 0.0

    reward += (next_state.xp - prev_state.xp) * 1.0
    reward += (next_state.level - prev_state.level) * 5.0
    reward += (next_state.health - prev_state.health) * 0.05

    opp_dist_prev = abs(prev_state.me_xy[0] - prev_state.opp_xy[0]) + abs(prev_state.me_xy[1] - prev_state.opp_xy[1])
    opp_dist_next = abs(next_state.me_xy[0] - next_state.opp_xy[0]) + abs(next_state.me_xy[1] - next_state.opp_xy[1])

    reward += (opp_dist_prev - opp_dist_next) * 0.1

    if done:
        reward += 10.0

    return reward


def new_game(base_url, p1_name, p2_name):
    """Pokrece novu igru i vraca (game_id, p1_id, p2_id, state_url, raw)."""
    game_id = start_game(base_url, p1_name, p2_name)
    connect_websocket(base_url, game_id)
    time.sleep(0.5)

    state_url = f"{base_url}/game/state/{game_id}"
    raw = requests.get(state_url, timeout=5).json()

    p1_id = str(find_my_player_id(raw, p1_name))
    p2_id = str(find_my_player_id(raw, p2_name))
    print(f"P1 ID={p1_id}  P2 ID={p2_id}")
    return game_id, p1_id, p2_id, state_url, raw


def print_turn(gs, player_name, command, state, reward):
    sep = "=" * 72
    print(sep)
    print(f"  {gs}  |  Igrac: {player_name}  |  Reward: {reward:+.2f}")
    action = command.get("Action", "?")
    if action == "Move":
        t = command.get("Target", {})
        print(f"  Potez: Move -> X={t.get('X')} Y={t.get('Y')}")
    elif action == "Attack":
        print(f"  Potez: Attack target={command.get('TargetId')}")
    elif action == "UseItem":
        print(f"  Potez: UseItem id={command.get('ItemId')}")
    elif action == "Pickup":
        t = command.get("Target", {})
        print(f"  Potez: Pickup X={t.get('X')} Y={t.get('Y')}")
    elif action == "Summon":
        t = command.get("Target", {})
        print(f"  Potez: Summon card={command.get('CardId')} -> X={t.get('X')} Y={t.get('Y')}")
    else:
        print(f"  Potez: {action}")
    print(f"  HP={state.health}/{state.max_health}  pos={state.me_xy}  opp={state.opp_xy}")
    print_map(state.map)


def main():
    game_id, p1_id, p2_id, state_url, raw = new_game(BASE_URL, BOT1_NAME, BOT2_NAME)

    # Odredi obs_dim iz prvog state-a (koristimo vec-fetchovani raw)
    init_state = parse_state(raw, p1_id)
    obs_dim = len(init_state.get_state_vector())
    print(f"obs_dim={obs_dim}")

    agent = PPO(obs_dim=obs_dim, action_dim=60)
    last_state = init_state

    for update in range(TOTAL_UPDATES):
        memory = make_memory()
        steps_collected = 0

        while steps_collected < ROLLOUT_STEPS:
            raw = requests.get(state_url, timeout=5).json()  # GET #1
            gs = raw.get("GameState", "")

            if gs == "Ending":
                memory["dones"][-1] = 1 if memory["dones"] else 0
                game_id, p1_id, p2_id, state_url, raw = new_game(BASE_URL, BOT1_NAME, BOT2_NAME)
                gs = raw.get("GameState", "")

            if gs == "Player1Turn":
                current_id = p1_id
                player_name = BOT1_NAME
            elif gs == "Player2Turn":
                current_id = p2_id
                player_name = BOT2_NAME
            else:
                # MonsterTurn — cekaj
                time.sleep(0.1)
                continue

            state = parse_state(raw, current_id)  # koristi GET #1, bez novog zahteva
            obs = state.get_state_vector()
            mask = build_action_mask(state)

            action_idx, logprob, value = agent.model.act(obs, mask)
            command = action_index_to_command(action_idx, state)
            prev_state = state

            try:
                send_api_command(BASE_URL, game_id, command)
            except Exception as e:
                print(f"Bad action [{gs}]:", command, e)

            time.sleep(0.05)

            next_raw = requests.get(state_url, timeout=5).json()  # GET #2
            done = next_raw.get("GameState", "") == "Ending"
            next_state = parse_state(next_raw, current_id)  # koristi GET #2, bez novog zahteva
            reward = reward_fn(prev_state, next_state, done)

            print_turn(gs, player_name, command, next_state, reward)

            memory["obs"].append(obs)
            memory["actions"].append(action_idx)
            memory["logprobs"].append(logprob)
            memory["values"].append(value)
            memory["rewards"].append(reward)
            memory["dones"].append(int(done))
            memory["masks"].append(mask)

            last_state = next_state
            steps_collected += 1

        # Bootstrap vrednost za poslednji state
        last_obs = last_state.get_state_vector()
        last_mask = build_action_mask(last_state)
        _, _, next_value = agent.model.act(last_obs, last_mask)

        agent.update(memory, next_value)
        print(f"Update {update}  steps={steps_collected}  "
              f"reward_sum={sum(memory['rewards']):.2f}")

        if update % 10 == 0:
            agent.save("ppo_model.pt")
            print(f"  -> Saved ppo_model.pt")

    agent.save("ppo_model_final.pt")


if __name__ == "__main__":
    main()