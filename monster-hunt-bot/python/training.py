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


def main():
    game_id = start_game(BASE_URL, BOT1_NAME, BOT2_NAME)

    connect_websocket(BASE_URL, game_id)
    time.sleep(0.5)  # cekaj da server predje u Player1Turn

    state_url = f"{BASE_URL}/game/state/{game_id}"

    # player_id dolazi iz game state, ne iz start responsa
    raw = requests.get(state_url, timeout=5).json()
    player_id = str(find_my_player_id(raw, BOT1_NAME))
    print(f"Player ID: {player_id}")

    state = get_state(state_url, player_id)
    obs_dim = len(state.get_state_vector())

    agent = PPO(obs_dim=obs_dim, action_dim=60)

    for update in range(TOTAL_UPDATES):
        memory = make_memory()

        for step in range(ROLLOUT_STEPS):
            state = get_state(state_url, player_id)

            obs = state.get_state_vector()
            mask = build_action_mask(state)

            action_idx, logprob, value = agent.model.act(obs, mask)

            command = action_index_to_command(action_idx, state)

            prev_state = state

            try:
                send_api_command(BASE_URL, game_id, command)
            except Exception as e:
                print("Bad action:", command, e)

            time.sleep(0.05)

            next_state = get_state(state_url, player_id)

            done = False
            reward = reward_fn(prev_state, next_state, done)

            memory["obs"].append(obs)
            memory["actions"].append(action_idx)
            memory["logprobs"].append(logprob)
            memory["values"].append(value)
            memory["rewards"].append(reward)
            memory["dones"].append(done)
            memory["masks"].append(mask)

        next_obs = next_state.get_state_vector()
        next_mask = build_action_mask(next_state)

        _, _, next_value = agent.model.act(next_obs, next_mask)

        agent.update(memory, next_value)

        if update % 10 == 0:
            agent.save("ppo_model.pt")
            print(f"Saved update {update}")

    agent.save("ppo_model_final.pt")


if __name__ == "__main__":
    main()