# train.py

import requests
import time
import numpy as np
from actions import *
from state import *

from ppo_agent import PPO, make_memory
# from your_code import get_state, build_action_mask, action_index_to_command, send_api_command

BASE_URL = "http://localhost:8080"
GAME_ID = "your-game-id"
PLAYER_ID = "your-player-id"

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
    state = get_state(f"{BASE_URL}/game/state/{GAME_ID}", PLAYER_ID)
    obs_dim = len(state.get_state_vector())

    agent = PPO(obs_dim=obs_dim, action_dim=60)

    for update in range(TOTAL_UPDATES):
        memory = make_memory()

        for step in range(ROLLOUT_STEPS):
            state = get_state(f"{BASE_URL}/game/state/{GAME_ID}", PLAYER_ID)

            obs = state.get_state_vector()
            mask = build_action_mask(state)

            action_idx, logprob, value = agent.model.act(obs, mask)

            command = action_index_to_command(action_idx, state)

            prev_state = state

            try:
                send_api_command(BASE_URL, GAME_ID, command)
            except Exception as e:
                print("Bad action:", command, e)

            time.sleep(0.05)

            next_state = get_state(f"{BASE_URL}/game/state/{GAME_ID}", PLAYER_ID)

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