# ppo_agent.py

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Categorical

# import from your files
# from state_file import get_state
# from action_file import build_action_mask, action_index_to_command, send_api_command, ACTION_SIZE

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class ActorCritic(nn.Module):
    def __init__(self, obs_dim, action_dim=60):
        super().__init__()

        self.shared = nn.Sequential(
            nn.Linear(obs_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU()
        )

        self.actor = nn.Linear(256, action_dim)
        self.critic = nn.Linear(256, 1)

    def forward(self, x):
        h = self.shared(x)
        return self.actor(h), self.critic(h)

    def act(self, obs, mask):
        obs = torch.tensor(obs, dtype=torch.float32, device=DEVICE).unsqueeze(0)
        mask = torch.tensor(mask, dtype=torch.bool, device=DEVICE).unsqueeze(0)

        logits, value = self.forward(obs)

        logits = logits.masked_fill(~mask, -1e9)
        dist = Categorical(logits=logits)

        action = dist.sample()
        logprob = dist.log_prob(action)

        return (
            action.item(),
            logprob.item(),
            value.item()
        )

    def evaluate(self, obs, actions, masks):
        logits, values = self.forward(obs)

        logits = logits.masked_fill(~masks.bool(), -1e9)
        dist = Categorical(logits=logits)

        logprobs = dist.log_prob(actions)
        entropy = dist.entropy()

        return logprobs, values.squeeze(-1), entropy


class PPO:
    def __init__(
        self,
        obs_dim,
        action_dim=60,
        lr=3e-4,
        gamma=0.99,
        gae_lambda=0.95,
        clip_eps=0.2,
        update_epochs=4,
        batch_size=64,
        value_coef=0.5,
        entropy_coef=0.05
    ):
        self.model = ActorCritic(obs_dim, action_dim).to(DEVICE)
        self.optimizer = optim.Adam(self.model.parameters(), lr=lr)

        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_eps = clip_eps
        self.update_epochs = update_epochs
        self.batch_size = batch_size
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef

    def compute_gae(self, rewards, values, dones, next_value):
        n = len(rewards)

        advantages = [0.0] * n
        returns = [0.0] * n

        gae = 0.0
        next_val = next_value

        for t in range(n - 1, -1, -1):
            not_done = 1.0 - dones[t]

            delta = rewards[t] + self.gamma * next_val * not_done - values[t]

            gae = delta + self.gamma * self.gae_lambda * not_done * gae

            advantages[t] = gae
            returns[t] = gae + values[t]

            next_val = values[t]

        return advantages, returns

    def update(self, all_env_data):
        """all_env_data: lista (memory, nv_p1, nv_p2) — po jedan unos po envu."""
        obs_all, actions_all, logprobs_all, masks_all, advantages, returns = [], [], [], [], [], []

        for memory, nv_p1, nv_p2 in all_env_data:
            adv_p1, ret_p1 = self.compute_gae(
                memory["rewards_p1"], memory["values_p1"], memory["dones_p1"], nv_p1
            )
            adv_p2, ret_p2 = self.compute_gae(
                memory["rewards_p2"], memory["values_p2"], memory["dones_p2"], nv_p2
            )
            obs_all      += memory["obs_p1"]      + memory["obs_p2"]
            actions_all  += memory["actions_p1"]  + memory["actions_p2"]
            logprobs_all += memory["logprobs_p1"] + memory["logprobs_p2"]
            masks_all    += memory["masks_p1"]    + memory["masks_p2"]
            advantages   += adv_p1 + adv_p2
            returns      += ret_p1 + ret_p2

        import random
        combined = list(zip(obs_all, actions_all, logprobs_all, masks_all, advantages, returns))
        random.shuffle(combined)
        obs_all, actions_all, logprobs_all, masks_all, advantages, returns = map(list, zip(*combined))

        obs = torch.tensor(np.array(obs_all), dtype=torch.float32, device=DEVICE)
        actions = torch.tensor(actions_all, dtype=torch.long, device=DEVICE)
        old_logprobs = torch.tensor(logprobs_all, dtype=torch.float32, device=DEVICE)
        masks = torch.tensor(np.array(masks_all), dtype=torch.bool, device=DEVICE)
        advantages = torch.tensor(advantages, dtype=torch.float32, device=DEVICE)
        returns = torch.tensor(returns, dtype=torch.float32, device=DEVICE)

        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

        n = len(obs)

        for _ in range(self.update_epochs):
            indices = torch.randperm(n)

            for start in range(0, n, self.batch_size):
                batch_idx = indices[start:start + self.batch_size]

                new_logprobs, values, entropy = self.model.evaluate(
                    obs[batch_idx],
                    actions[batch_idx],
                    masks[batch_idx]
                )

                ratio = torch.exp(new_logprobs - old_logprobs[batch_idx])

                surr1 = ratio * advantages[batch_idx]
                surr2 = torch.clamp(
                    ratio,
                    1 - self.clip_eps,
                    1 + self.clip_eps
                ) * advantages[batch_idx]

                actor_loss = -torch.min(surr1, surr2).mean()
                critic_loss = nn.functional.mse_loss(values, returns[batch_idx])
                entropy_loss = entropy.mean()

                loss = (
                    actor_loss
                    + self.value_coef * critic_loss
                    - self.entropy_coef * entropy_loss
                )

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.model.parameters(), 0.5)
                self.optimizer.step()

    def save(self, path="ppo_model.pt"):
        torch.save(self.model.state_dict(), path)

    def load(self, path="ppo_model.pt"):
        self.model.load_state_dict(torch.load(path, map_location=DEVICE))


def make_memory():
    return {
        "obs_p1": [], "actions_p1": [], "logprobs_p1": [],
        "rewards_p1": [], "values_p1": [], "dones_p1": [], "masks_p1": [],
        "obs_p2": [], "actions_p2": [], "logprobs_p2": [],
        "rewards_p2": [], "values_p2": [], "dones_p2": [], "masks_p2": [],
    }