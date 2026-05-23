# train.py

import requests
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


_TURN_NAMES = {"1": "Player1Turn", "2": "Player2Turn", "3": "MonsterTurn"}


def _parse_ws_frames(buf):
    """Parsira WebSocket frejmove iz bajtova. Vraca (lista poruka, ostatak bafera)."""
    import struct, json
    messages = []
    i = 0
    while i + 2 <= len(buf):
        b0, b1 = buf[i], buf[i + 1]
        payload_len = b1 & 0x7F
        i += 2
        if payload_len == 126:
            if i + 2 > len(buf): break
            payload_len = struct.unpack(">H", buf[i:i+2])[0]; i += 2
        elif payload_len == 127:
            if i + 8 > len(buf): break
            payload_len = struct.unpack(">Q", buf[i:i+8])[0]; i += 8
        if i + payload_len > len(buf): break
        payload = buf[i:i + payload_len]
        i += payload_len
        if (b0 & 0x0F) == 1:  # text frame
            try:
                messages.append(json.loads(payload.decode("utf-8")))
            except Exception:
                pass
    return messages, buf[i:]


def connect_websocket(base_url, game_id):
    """Konektuje se na WS i vraca (thread, turn_event).
    turn_event se setuje svaki put kad server posalje Type:15 (promena tura)."""
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

    turn_event = threading.Event()

    def run():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        sock.sendall(handshake.encode())
        resp = sock.recv(4096)
        if b"101" not in resp:
            print(f"[WS] handshake failed: {resp[:200]}")
            return
        print(f"[WS] connected for {game_id}")
        header_end = resp.find(b"\r\n\r\n")
        buf = resp[header_end + 4:] if header_end != -1 else b""
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                msgs, buf = _parse_ws_frames(buf)
                for msg in msgs:
                    if msg.get("Type") == 15:
                        turn_name = _TURN_NAMES.get(str(msg.get("Data", "")), "?")
                        print(f"[WS] turn -> {turn_name}")
                        if turn_name != "MonsterTurn":
                            turn_event.set()
            except Exception:
                break
        sock.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, turn_event

ROLLOUT_STEPS = 512
TOTAL_UPDATES = 1000


def is_collapse_tile(x, y, phase):
    # PHASE 1: outer 3 columns
    if phase >= 1:
        if x <= 2 or x >= MAP_W - 3:
            return True

    # PHASE 2: 3 more columns from each side
    if phase >= 2:
        if x <= 5 or x >= MAP_W - 6:
            return True

    # PHASE 3: bridges
    if phase >= 3:
        # left-side bridges
        if 6 <= x <= 12 and (0 <= y <= 3 or 12 <= y <= 15):
            return True

        # mirrored right-side bridges
        mx = MAP_W - 1 - x
        if 6 <= mx <= 12 and (0 <= y <= 3 or 12 <= y <= 15):
            return True

    return False


def reward_fn(prev_state, next_state, done=False):
    reward = 0.0

    hp_diff = next_state.health - prev_state.health
    reward += hp_diff * 0.15

    opp_hp_diff = prev_state.opp_health - next_state.opp_health
    reward += opp_hp_diff * 0.25

    # dying is VERY bad
    if next_state.health <= 0:
        reward -= 20.0

    # opponent hp drop
    # estimated from xp gain
    xp_diff = next_state.xp - prev_state.xp
    reward += xp_diff * 0.2


    level_diff = next_state.level - prev_state.level
    reward += level_diff * 15.0


    prev_dist = (
        abs(prev_state.me_xy[0] - prev_state.opp_xy[0]) +
        abs(prev_state.me_xy[1] - prev_state.opp_xy[1])
    )

    next_dist = (
        abs(next_state.me_xy[0] - next_state.opp_xy[0]) +
        abs(next_state.me_xy[1] - next_state.opp_xy[1])
    )

    # reward approaching enemy slightly
    reward += (prev_dist - next_dist) * 0.05

    if next_state.inventory[0] != 0:
        reward += 2
    if next_state.inventory[1] != 0:
        reward += 2
    if next_state.inventory[2] != 0:
        reward += 2

    if next_state.cards[0] != 0:
        reward += 3
    if next_state.cards[1] != 0:
        reward += 3
    if next_state.cards[2] != 0:
        reward += 3

    prev_frozen = "Frozen" in prev_state.statuses
    next_frozen = "Frozen" in next_state.statuses

    prev_confused = "Confused" in prev_state.statuses
    next_confused = "Confused" in next_state.statuses

    if not prev_frozen and next_frozen:
        reward -= 4.0

    if not prev_confused and next_confused:
        reward -= 3.0

    x, y = next_state.me_xy
    opp_x, opp_y = next_state.opp_xy

    tile = next_state.map[x * MAP_H + y]

    if tile == Field.SPIKES:
        reward -= 1.0

    if tile == Field.SNOW:
        reward -= 0.15

    phase = next_state.turn_counter // 15
    next_phase = phase + 1
    turns_until_collapse = 15 - (next_state.turn_counter % 15)

    if is_collapse_tile(x, y, phase):
        reward -= 15.0

    elif turns_until_collapse <= 3 and is_collapse_tile(x, y, next_phase):
        reward -= 3.0

    if turns_until_collapse <= 3 and is_collapse_tile(opp_x, opp_y, next_phase):
        reward += 4.0

    if done:
        if next_state.health > 0:
            reward += 50.0
        else:
            reward -= 50.0

    reward = np.clip(reward, -50.0, 50.0)

    return float(reward)


def new_game(base_url, p1_name, p2_name):
    """Pokrece novu igru i vraca (game_id, p1_id, p2_id, state_url, raw, turn_event)."""
    game_id = start_game(base_url, p1_name, p2_name)
    _, turn_event = connect_websocket(base_url, game_id)
    # Cekaj WS Type:15 (Start -> Player1Turn) umesto fiksnog sleep-a
    turn_event.wait(timeout=3)
    turn_event.clear()

    state_url = f"{base_url}/game/state/{game_id}"
    raw = requests.get(state_url, timeout=5).json()

    p1_id = str(find_my_player_id(raw, p1_name))
    p2_id = str(find_my_player_id(raw, p2_name))
    print(f"P1 ID={p1_id}  P2 ID={p2_id}")
    return game_id, p1_id, p2_id, state_url, raw, turn_event


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
    game_id, p1_id, p2_id, state_url, raw, turn_event = new_game(BASE_URL, BOT1_NAME, BOT2_NAME)

    init_state = parse_state(raw, p1_id)
    obs_dim = len(init_state.get_state_vector())
    print(f"obs_dim={obs_dim}")

    agent = PPO(obs_dim=obs_dim, action_dim=60)
    last_state = init_state
    current_raw = raw  # nose stanje izmedju tura — eliminise redundantni GET #1

    for update in range(TOTAL_UPDATES):
        memory = make_memory()
        steps_collected = 0

        while steps_collected < ROLLOUT_STEPS:
            # Ako nemamo stanje (MonsterTurn prethodne iteracije), cekaj WS + GET
            if current_raw is None:
                turn_event.wait(timeout=10)
                turn_event.clear()
                current_raw = requests.get(state_url, timeout=5).json()

            gs = current_raw.get("GameState", "")

            if gs == "Player1Turn":
                current_id = p1_id
                player_name = BOT1_NAME
            elif gs == "Player2Turn":
                current_id = p2_id
                player_name = BOT2_NAME
            else:
                # MonsterTurn: odbaci stanje i cekaj sledeci signal
                current_raw = None
                continue

            state = parse_state(current_raw, current_id)
            obs = state.get_state_vector()
            mask = build_action_mask(state)

            action_idx, logprob, value = agent.model.act(obs, mask)
            command = action_index_to_command(action_idx, state)
            prev_state = state

            try:
                send_api_command(BASE_URL, game_id, command)
            except Exception as e:
                print(f"Bad action [{gs}]:", command, e)

            # Cekaj WS potvrdu da je turn promenjen, zatim GET (jedini GET po potezu)
            turn_event.wait(timeout=6)
            turn_event.clear()
            current_raw = requests.get(state_url, timeout=5).json()

            done = current_raw.get("GameState", "") == "Ending"
            next_state = parse_state(current_raw, current_id)
            reward = reward_fn(prev_state, next_state, done)

            action = command.get("Action", "?")
            target = command.get("Target", command.get("TargetId", ""))
            print(f"[{gs}] {player_name}: {action} {target}  HP={next_state.health}/{next_state.max_health}  reward={reward:+.2f}")

            memory["obs"].append(obs)
            memory["actions"].append(action_idx)
            memory["logprobs"].append(logprob)
            memory["values"].append(value)
            memory["rewards"].append(reward)
            memory["dones"].append(int(done))
            memory["masks"].append(mask)

            print("Game ending:", done)
            if done:
                game_id, p1_id, p2_id, state_url, current_raw, turn_event = new_game(
                    BASE_URL, BOT1_NAME, BOT2_NAME
                )
                last_state = parse_state(current_raw, p1_id)
            else:
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