# =========================
# ACTION PARSER + API SENDER
# =========================

from state import *

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

    try:
        # connect timeout=5s, read timeout=1s
        # Server blokira PUT dok ceka drugog igraca (do 5s), ali potez je
        # vec obradjeno cim server primi zahtev — ne treba nam odgovor.
        if body is None:
            response = requests.put(url, timeout=(5, 1))
        else:
            response = requests.put(url, json=body, timeout=(5, 1))
    except requests.exceptions.ReadTimeout:
        return None  # potez obradjeno, server samo nije odgovorio na vreme

    if response.status_code not in (200, 201, 204, 400):
        raise Exception(f"API command failed: {response.status_code} {response.text}")

    return response.json() if response.text else None

PICKUP_ITEM_NAMES = ["Potion", "Freeze", "Confusion", "Card1", "Card2", "Card3"]
PICKUP_DIR_NAMES  = ["UP", "DOWN", "LEFT", "RIGHT"]

def print_action_mask(mask):
    m = np.asarray(mask, dtype=np.int8)

    print("=== ACTION MASK ===")

    # MOVE [0..15]  4 directions x 4 steps
    print(f"\nMOVE [0..15]:")
    for dir_idx, name in enumerate(DIRECTION_NAMES):
        base = MOVE_START + dir_idx * 4
        bits = m[base:base + 4].tolist()
        reachable = [str(s + 1) for s, v in enumerate(bits) if v]
        print(f"  {name:6s}: {bits}  -> steps {reachable if reachable else '—'}")

    # PICKUP [16..39]  6 items x 4 directions
    print(f"\nPICKUP [16..39]:")
    for item_idx, item_name in enumerate(PICKUP_ITEM_NAMES):
        base = PICKUP_START + item_idx * 4
        bits = m[base:base + 4].tolist()
        dirs = [PICKUP_DIR_NAMES[d] for d, v in enumerate(bits) if v]
        print(f"  {item_name:10s}: {bits}  -> {dirs if dirs else '—'}")

    # USE_ITEM [40..42]
    print(f"\nUSE_ITEM [40..42]:")
    for i, name in enumerate(["Potion", "Freeze", "Confusion"]):
        print(f"  {name:10s}: {m[USE_ITEM_START + i]}")

    # ATTACK_PLAYER [43]
    print(f"\nATTACK_PLAYER [43]: {m[ATTACK_PLAYER_IDX]}")

    # ATTACK_MONSTER [44..47]
    print(f"\nATTACK_MONSTER [44..47]:")
    for dir_idx, name in enumerate(DIRECTION_NAMES):
        print(f"  {name:6s}: {m[ATTACK_MONSTER_START + dir_idx]}")

    # SUMMON [48..59]  3 cards x 4 directions
    print(f"\nSUMMON [48..59]:")
    for card_idx in range(3):
        base = SUMMON_START + card_idx * 4
        bits = m[base:base + 4].tolist()
        dirs = [DIRECTION_NAMES[d] for d, v in enumerate(bits) if v]
        print(f"  Card{card_idx + 1}     : {bits}  -> {dirs if dirs else '—'}")

    print(f"\nTotal: {m.sum()} valid actions / {len(m)}")
    print("===================")


if __name__ == "__main__":
    url = "http://localhost:8080"
    game_id = "13b432a2-ba8c-4241-9895-10429b187d2a"
    bot_name = "asd"

    response = requests.get(f"{url}/game/state/{game_id}", timeout=5)
    data = response.json() if response.status_code == 200 else None
    if data is None:
        raise Exception("Problem parsing state")

    player_id = find_my_player_id(data, bot_name)

    # # Napravi map_grid dict
    # map_grid = {}
    # for field in data["Map"]["Grid"]:
    #     pos = field["Position"]
    #     x, y = pos["X"], pos["Y"]
    #     tile = convertToField(field, player_id)
    #     map_grid[(x, y)] = tile if tile is not None else Field.NORMAL
    # if player_id is None:
    #     raise Exception(f"Igrac '{bot_name}' nije nadjen")

    player = data["Players"][str(player_id)]
    state = get_state(f"{url}/game/state/{game_id}", str(player_id))

    # print_map(state.map)

    my_pos = (player["Position"]["X"], player["Position"]["Y"])
    print(f"Igrac '{bot_name}' ID={player_id} na poziciji {my_pos}")

    # Moguca kretanja
    moves = get_possible_moves(state.map, my_pos)
    print(f"\nMoguca kretanja ({len(moves)}):")
    for dest, cost in sorted(moves.items()):
        tile = state.map[dest[0] * MAP_H + dest[1]]
        print(f"  X={dest[0]}  Y={dest[1]}  stamina={cost}  tile={tile.name}")

    print(get_move_vector(state.map, my_pos))

    # Moguce pozicije za summon
    cards = player.get("Cards") or []
    summon_vecs = get_summon_vectors(state.map, my_pos, cards)

    DIRECTION_NAMES = ["LEFT", "RIGHT", "UP", "DOWN"]
    if summon_vecs:
        for i, (card, vector) in enumerate(summon_vecs):
            card_name = card.get("Name", "?")
            card_id = card.get("Id", "?")
            print(f"\nKarta [{i}] '{card_name}' (ID={card_id}) — vektor={vector.tolist()}:")
            for dir_idx, can_summon in enumerate(vector):
                if can_summon:
                    dx, dy = DIRECTIONS[dir_idx]
                    sx, sy = my_pos[0] + dx, my_pos[1] + dy
                    tile = state.map[sx * MAP_H + sy]
                    print(f"  {DIRECTION_NAMES[dir_idx]} -> X={sx}  Y={sy}  tile={tile.name}")
    else:
        print("\nNema dostupnih karata za postavljanje")

    action_masks = get_possible_pickups(state, my_pos)
    mask_vector = flatten_possible_pickups(action_masks)
    print(mask_vector)
    print(mask_vector.shape)  # (24,)

    inventory_vector = get_inventory_vector(state.inventory)
    print("\nInventory vector:")
    print(inventory_vector)

    print(state.can_attack_player())
    print(state.monster_attack_vector())

    print_action_mask(build_action_mask(state))