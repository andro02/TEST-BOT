import time
import requests
import torch

from state import parse_state, find_my_player_id
from actions import build_action_mask, action_index_to_command, send_api_command
from ppo import PPO


MODEL_PATH = "ppo_model_final.pt"
BASE_URL = "http://localhost:8080"
GAME_ID = "YOUR_GAME_ID"
BOT_NAME = "asd"

ACTION_DIM = 60


def load_agent(model_path, obs_dim):
    agent = PPO(obs_dim=obs_dim, action_dim=ACTION_DIM)

    checkpoint = torch.load(model_path, map_location="cpu")

    if isinstance(checkpoint, dict):
        if "model_state_dict" in checkpoint:
            agent.model.load_state_dict(checkpoint["model_state_dict"])
        elif "state_dict" in checkpoint:
            agent.model.load_state_dict(checkpoint["state_dict"])
        else:
            agent.model.load_state_dict(checkpoint)
    else:
        agent.model.load_state_dict(checkpoint)

    agent.model.eval()
    return agent


def predict_command(agent, state):
    obs = state.get_state_vector()
    mask = build_action_mask(state)

    with torch.no_grad():
        action_idx, _, _ = agent.model.act(obs, mask)

    command = action_index_to_command(action_idx, state)

    return action_idx, command


def main():
    state_url = f"{BASE_URL}/game/state/{GAME_ID}"

    raw = requests.get(state_url, timeout=5).json()

    player_id = str(find_my_player_id(raw, BOT_NAME))

    if player_id == "None":
        raise Exception(f"Player '{BOT_NAME}' not found")

    init_state = parse_state(raw, player_id)

    obs_dim = len(init_state.get_state_vector())

    print(f"obs_dim={obs_dim}")

    agent = load_agent(MODEL_PATH, obs_dim)

    print(f"Loaded model: {MODEL_PATH}")

    while True:
        raw = requests.get(state_url, timeout=5).json()

        game_state = raw.get("GameState", "")

        if game_state == "Ending":
            print("Game ended")
            break

        if game_state not in ("Player1Turn", "Player2Turn"):
            time.sleep(0.1)
            continue

        state = parse_state(raw, player_id)

        action_idx, command = predict_command(agent, state)

        print(f"\naction_idx={action_idx}")
        print(command)

        try:
            send_api_command(BASE_URL, GAME_ID, command)
        except Exception as e:
            print("Failed to send command:", e)

        time.sleep(0.2)


if __name__ == "__main__":
    main()