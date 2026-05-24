import requests
import torch

from state import parse_state, find_my_player_id
from actions import build_action_mask, action_index_to_command, send_api_command
from ppo import PPO, DEVICE
from training import connect_websocket

MODEL_PATH = "ppo_model.pt"
BASE_URL = "http://localhost:8080"
GAME_ID = "YOUR_GAME_ID"
BOT_NAME = "asd"

ACTION_DIM = 60


def load_agent(model_path, obs_dim):
    agent = PPO(obs_dim=obs_dim, action_dim=ACTION_DIM)
    agent.load(model_path)
    agent.model.eval()
    return agent


def greedy_act(agent, state):
    obs = torch.tensor(state.get_state_vector(), dtype=torch.float32, device=DEVICE).unsqueeze(0)
    mask = torch.tensor(build_action_mask(state), dtype=torch.bool, device=DEVICE).unsqueeze(0)
    with torch.no_grad():
        logits, _ = agent.model(obs)
        logits = logits.masked_fill(~mask, -1e9)
        action_idx = logits.argmax(dim=-1).item()
    return action_idx, action_index_to_command(action_idx, state)


def main():
    state_url = f"{BASE_URL}/game/state/{GAME_ID}"
    raw = requests.get(state_url, timeout=5).json()

    player_id = str(find_my_player_id(raw, BOT_NAME))
    if player_id == "None":
        raise Exception(f"Player '{BOT_NAME}' not found in game {GAME_ID}")

    obs_dim = len(parse_state(raw, player_id).get_state_vector())
    print(f"obs_dim={obs_dim}  player_id={player_id}")

    agent = load_agent(MODEL_PATH, obs_dim)
    print(f"Loaded: {MODEL_PATH}")

    _, turn_event = connect_websocket(BASE_URL, GAME_ID)

    while True:
        turn_event.wait(timeout=30)
        turn_event.clear()

        raw = requests.get(state_url, timeout=5).json()
        gs = raw.get("GameState", "")

        if gs == "Ending":
            print("Game ended")
            break

        if gs not in ("Player1Turn", "Player2Turn"):
            continue

        state = parse_state(raw, player_id)
        action_idx, command = greedy_act(agent, state)
        print(f"[{gs}] idx={action_idx}  {command['Action']}  HP={state.health}/{state.max_health}  pos={state.me_xy}")

        try:
            send_api_command(BASE_URL, GAME_ID, command)
        except Exception as e:
            if "409" not in str(e):
                print("Error:", e)


if __name__ == "__main__":
    main()
