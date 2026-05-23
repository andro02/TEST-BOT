# =========================
# ACTION PARSER + API SENDER
# =========================

MOVE_START = 0
PICKUP_START = 16
USE_ITEM_START = 40
ATTACK_PLAYER_IDX = 43
ATTACK_MONSTER_START = 44
SUMMON_START = 48

ACTION_SIZE = 60

DIRECTION_NAMES = ["LEFT", "RIGHT", "UP", "DOWN"]
PICKUP_DIRECTIONS = [(0, 1), (0, -1), (-1, 0), (1, 0)]

ITEM_ORDER = [
    Field.POTION,
    Field.FREEZE,
    Field.CONFUSION
]


def argmax_valid(logits, mask):
    logits = np.asarray(logits, dtype=float).reshape(-1)
    mask = np.asarray(mask, dtype=np.int8).reshape(-1)

    if logits.shape[0] != mask.shape[0]:
        raise ValueError(f"logits size {logits.shape[0]} != mask size {mask.shape[0]}")

    masked = logits.copy()
    masked[mask == 0] = -1e9

    if np.all(masked == -1e9):
        return None

    return int(np.argmax(masked))


def build_action_mask(state):
    my_pos = state.me_xy

    move_mask = get_move_vector(state.map, my_pos)  # 16

    pickup_mask = flatten_possible_pickups(
        get_possible_pickups(state, my_pos)
    )  # 24

    item_mask = get_inventory_vector(state.inventory)  # 3

    attack_player_mask = np.array(
        [1 if state.can_attack_player() else 0],
        dtype=np.int8
    )  # 1

    attack_monster_mask = state.monster_attack_vector()  # 4

    summon_mask = np.zeros(12, dtype=np.int8)

    base_summon_vector = get_summon_base_vector(state.map, my_pos)

    for card_idx in range(min(3, len(state.cards))):
        cooldown = state.monster_cooldowns[card_idx]

        if cooldown <= 0:
            summon_mask[card_idx * 4:(card_idx + 1) * 4] = base_summon_vector

    full_mask = np.concatenate([
        move_mask,
        pickup_mask,
        item_mask,
        attack_player_mask,
        attack_monster_mask,
        summon_mask
    ]).astype(np.int8)

    if full_mask.shape[0] != ACTION_SIZE:
        raise ValueError(f"Action mask size {full_mask.shape[0]} != {ACTION_SIZE}")

    return full_mask


def get_summon_base_vector(state_map, pos):
    BLOCKED = {
        Field.WALL,
        Field.EMPTY,
        Field.SPIKES,
        Field.FREEZE,
        Field.CONFUSION,
        Field.POTION,
        Field.MY_MONSTER_1,
        Field.MY_MONSTER_2,
        Field.MY_MONSTER_3,
        Field.ENEMY_MONSTER_1,
        Field.ENEMY_MONSTER_2,
        Field.ENEMY_MONSTER_3,
        Field.OPPONENT,
        Field.MONSTER_CARD_1,
        Field.MONSTER_CARD_2,
        Field.MONSTER_CARD_3
    }

    x, y = pos
    vector = np.zeros(4, dtype=np.int8)

    for dir_idx, (dx, dy) in enumerate(DIRECTIONS):
        nx, ny = x + dx, y + dy

        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            continue

        tile = state_map[nx * MAP_H + ny]

        if tile not in BLOCKED:
            vector[dir_idx] = 1

    return vector


def parse_action(nn_output, state):
    action_mask = build_action_mask(state)
    action_idx = argmax_valid(nn_output, action_mask)

    if action_idx is None:
        return {"Action": "Skip"}

    return action_index_to_command(action_idx, state)


def action_index_to_command(idx, state):
    x, y = state.me_xy

    if MOVE_START <= idx < PICKUP_START:
        local = idx - MOVE_START
        dir_idx = local // 4
        steps = local % 4 + 1

        dx, dy = DIRECTIONS[dir_idx]

        return {
            "Action": "Move",
            "PlayerId": state.player_id,
            "Target": {
                "X": x + dx * steps,
                "Y": y + dy * steps
            }
        }

    if PICKUP_START <= idx < USE_ITEM_START:
        local = idx - PICKUP_START
        dir_idx = local % 4

        dx, dy = PICKUP_DIRECTIONS[dir_idx]

        return {
            "Action": "Pickup",
            "PlayerId": state.player_id,
            "Target": {
                "X": x + dx,
                "Y": y + dy
            }
        }

    if USE_ITEM_START <= idx < ATTACK_PLAYER_IDX:
        item_idx = idx - USE_ITEM_START
        item_type = ITEM_ORDER[item_idx]

        item_id = state.item_ids.get(item_type)

        if item_id is None:
            return {"Action": "Skip"}

        return {
            "Action": "UseItem",
            "PlayerId": state.player_id,
            "ItemId": item_id
        }

    if idx == ATTACK_PLAYER_IDX:
        return {
            "Action": "Attack",
            "AttackerId": state.player_id,
            "TargetId": state.opp_id
        }

    if ATTACK_MONSTER_START <= idx < SUMMON_START:
        dir_idx = idx - ATTACK_MONSTER_START
        target_id = get_adjacent_enemy_monster_id(state, dir_idx)

        if target_id is None:
            return {"Action": "Skip"}

        return {
            "Action": "Attack",
            "AttackerId": state.player_id,
            "TargetId": target_id
        }

    if SUMMON_START <= idx < ACTION_SIZE:
        local = idx - SUMMON_START
        card_idx = local // 4
        dir_idx = local % 4

        if card_idx >= len(state.card_ids):
            return {"Action": "Skip"}

        if state.monster_cooldowns[card_idx] > 0:
            return {"Action": "Skip"}

        dx, dy = DIRECTIONS[dir_idx]

        return {
            "Action": "Summon",
            "PlayerId": state.player_id,
            "CardId": state.card_ids[card_idx],
            "Target": {
                "X": x + dx,
                "Y": y + dy
            }
        }

    return {"Action": "Skip"}


def get_adjacent_enemy_monster_id(state, dir_idx):
    x, y = state.me_xy
    dx, dy = DIRECTIONS[dir_idx]

    nx, ny = x + dx, y + dy

    if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
        return None

    return state.enemy_monster_ids_by_pos.get((nx, ny))


def send_api_command(base_url, game_id, command):
    action = command["Action"]

    if action == "Skip":
        return None

    if action == "Move":
        url = f"{base_url}/player/move/gameId/{game_id}"
        body = {
            "playerId": command["PlayerId"],
            "newPosition": command["Target"]
        }

    elif action == "Attack":
        url = (
            f"{base_url}/player/{command['AttackerId']}"
            f"/attack/{command['TargetId']}/gameId/{game_id}"
        )
        body = None

    elif action == "UseItem":
        url = (
            f"{base_url}/player/{command['PlayerId']}"
            f"/use-item/{command['ItemId']}/gameId/{game_id}"
        )
        body = None

    elif action == "Pickup":
        url = f"{base_url}/player/pickup/{command['PlayerId']}/gameId/{game_id}"
        body = {
            "Position": command["Target"]
        }

    elif action == "Summon":
        url = (
            f"{base_url}/map/{command['PlayerId']}"
            f"/summon/{command['CardId']}/gameId/{game_id}"
        )
        body = command["Target"]

    else:
        raise ValueError(f"Unknown action: {action}")

    if body is None:
        response = requests.put(url, timeout=5)
    else:
        response = requests.put(url, json=body, timeout=5)

    if response.status_code not in (200, 201, 204):
        raise Exception(f"API command failed: {response.status_code} {response.text}")

    return response.json() if response.text else None