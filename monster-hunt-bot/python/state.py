import numpy as np
from enum import Enum
import requests


def pad_list(my_list, target_size, padding_value):
    if len(my_list) < target_size:
        my_list.extend([padding_value] * (target_size - len(my_list)))


class TileType(Enum):
    BASE = 0
    NORMAL = 1
    OBSTACLE_SLOW = 2
    OBSTACLE = 3
    POWERUP = 4
    WALL = 5
    EMPTY = 6


def convertToField(map_field, player_id):

    if map_field["Item"] is not None and map_field["Item"]["Name"] is not None:
        if map_field["Item"]["Name"] == "Kristal života":
            return Field.POTION
        elif map_field["Item"]["Name"] == "Freeze scroll":
            return Field.FREEZE
        elif map_field["Item"]["Name"] == "Dizzy scroll":
            return Field.CONFUSION

    if map_field["MonsterCard"] is not None:
        if map_field["MonsterCard"]["Name"] == "Card of Ice Cubes":
            return Field.MONSTER_CARD_1
        elif map_field["MonsterCard"]["Name"] == "Card of Ice Mage":
            return Field.MONSTER_CARD_2
        elif "card" in map_field["MonsterCard"]["Name"].lower():
            return Field.MONSTER_CARD_3

    if map_field["Entity"] is not None and "Name" in map_field["Entity"]:
        if map_field["Entity"]["Name"] == "Ice cube":
            if map_field["Entity"]["SummonedByPlayerId"] == player_id:
                return Field.MY_MONSTER_1
            else:
                return Field.ENEMY_MONSTER_1
        elif map_field["Entity"]["Name"] == "Ice Mage":
            if map_field["Entity"]["SummonedByPlayerId"] == player_id:
                return Field.MY_MONSTER_2
            else:
                return Field.ENEMY_MONSTER_2
        elif map_field["Entity"]["Name"] == "Ice Warrior":
            if map_field["Entity"]["SummonedByPlayerId"] == player_id:
                return Field.MY_MONSTER_3
            else:
                return Field.ENEMY_MONSTER_3

    if map_field["FieldType"] == TileType.NORMAL.value:
        return Field.NORMAL
    elif map_field["FieldType"] == TileType.OBSTACLE_SLOW.value:
        return Field.SNOW
    elif map_field["FieldType"] == TileType.OBSTACLE.value:
        return Field.SPIKES
    elif map_field["FieldType"] == TileType.WALL.value:
        return Field.WALL
    elif map_field["FieldType"] == TileType.EMPTY.value:
        return Field.EMPTY

    if map_field["FieldType"] == TileType.BASE or map_field["FieldType"] == TileType.NORMAL:
        return Field.NORMAL
    return None



class Field(Enum):
    NORMAL = 1
    SNOW = 2 #obstacle slow
    SPIKES = 3 # obstacle
    WALL  = 4
    EMPTY = 5
#   POWERUPS
    POTION = 6
    CONFUSION = 7
    FREEZE = 8
    MY_MONSTER_1 = 9
    MY_MONSTER_2 = 10
    MY_MONSTER_3 = 11
#   MONSTER CARDS
    MONSTER_CARD_1 = 12
    MONSTER_CARD_2 = 13
    MONSTER_CARD_3 = 14
#   PLAYERS
    ME = 15
    OPPONENT = 16
    ENEMY_MONSTER_1 = 17
    ENEMY_MONSTER_2 = 18
    ENEMY_MONSTER_3 = 19

class State(object):
    def __init__(self, player_id, opp_id, max_health, attack_dmg, health, level, xp, inventory, cards, monster_cooldowns, map, statuses, statuses_lasting, me_xy, opp_xy):
        # self.health = 100
        # self.level = 0
        # self.xp = 0
        # # 1 potion, 2 confusion, 3 freeze
        # self.inventory = [0, 0, 0]
        # # 1 je monster 1, 2 monster 2, 3 monster 3
        # self.cards = [0, 0, 0]
        # # koliko monstera posedujem 1. pozicija za kolicinu monster 1, 2. pozicija za kolicinu monster 2, 3. pozicija za kolicinu monster 3
        # self.monsters = [0, 0, 0]
        # # koliko poteza dok ne mogu opet koristim sledeceg monstera
        # self.monster_cooldowns = [0, 0, 0]
        # # kolekcija enuma Field
        # self.map = np.zeros((32, 16))
        # # koji status imam i koliko traje jos
        # self.status = [0, 0]
        self.player_id = int(player_id)
        self.opp_id = int(opp_id)
        self.max_health = max_health
        self.attack_dmg = attack_dmg
        self.health = health
        self.level = level
        self.xp = xp
        # 1 potion, 2 confusion, 3 freeze
        self.inventory = inventory
        # 1 je monster 1, 2 monster 2, 3 monster 3
        self.cards = cards
        # koliko poteza dok ne mogu opet koristim sledeceg monstera
        self.monster_cooldowns = monster_cooldowns
        # kolekcija enuma Field
        self.map = map
        # koji status imam i koliko traje jos
        self.statuses = statuses
        self.statuses_lasting = statuses_lasting
        self.me_xy = me_xy
        self.opp_xy = opp_xy

    # Poznati statusi — za fiksnu enkodiranu poziciju u vektoru
    _STATUS_IDX = {"Confused": 0, "Frozen": 1}
    _MAX_STATUSES = 2
    _MAX_INVENTORY = 3
    _MAX_CARDS = 3

    def get_state_vector(self):
        # inventory: Field enum -> .value, pad na 3
        inv = [f.value for f in self.inventory]
        inv += [0] * (self._MAX_INVENTORY - len(inv))

        # cards: Field enum -> .value, pad na 3
        cards = [f.value for f in self.cards]
        cards += [0] * (self._MAX_CARDS - len(cards))

        # cooldowns: pad na 3
        cds = list(self.monster_cooldowns)
        cds += [0] * (self._MAX_CARDS - len(cds))

        # statuses: svaki poznati status dobija slot za trajanje (0 = neaktivan)
        status_vec = [0] * self._MAX_STATUSES
        for name, duration in zip(self.statuses, self.statuses_lasting):
            idx = self._STATUS_IDX.get(name)
            if idx is not None:
                status_vec[idx] = int(duration)

        # map: Field enum -> .value (512 elemenata)
        map_vals = [f.value for f in self.map]

        state_vector = np.array(
            [self.health, self.level, self.xp, self.max_health, self.attack_dmg]
            + inv
            + cards
            + cds
            + map_vals
            + status_vec
            + list(self.me_xy)
            + list(self.opp_xy),
            dtype=np.float32
        )
        return state_vector

    def can_attack_player(self):
        return abs(self.me_xy[0] - self.opp_xy[0]) + abs(self.me_xy[1] - self.opp_xy[1]) == 1

    def monster_attack_vector(self):
        x, y = self.me_xy

        directions = [
            (-1, 0),  # LEFT
            (1, 0),  # RIGHT
            (0, -1),  # UP
            (0, 1)  # DOWN
        ]

        vector = np.zeros(4, dtype=np.int8)

        for i, (dx, dy) in enumerate(directions):
            nx, ny = x + dx, y + dy

            if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                continue

            tile = self.map[nx * MAP_H + ny]
            if tile in [Field.ENEMY_MONSTER_1, Field.ENEMY_MONSTER_2, Field.ENEMY_MONSTER_3]:
                vector[i] = 1

        return vector


def parse_state(data, player_id):
    id_to_entity = {}
    def collect_ids(obj):
        if isinstance(obj, dict):
            if "$id" in obj:
                id_to_entity[obj["$id"]] = obj
            for v in obj.values():
                collect_ids(v)
        elif isinstance(obj, list):
            for item in obj:
                collect_ids(item)
    collect_ids(data)

    map = []
    for field in data["Map"]["Grid"]:
        entity = field.get("Entity")
        if isinstance(entity, dict) and "$ref" in entity:
            resolved = id_to_entity.get(entity["$ref"])
            if resolved:
                field = dict(field)
                field["Entity"] = resolved
        tile = convertToField(field, player_id)
        map.append(tile if tile is not None else Field.NORMAL)

    hp = data["Players"][player_id]["Health"]
    max_hp = data["Players"][player_id]["MaxHealth"]
    attack_dmg = data["Players"][player_id]["AttackPower"]
    xp = data["Players"][player_id]["Xp"]
    level = data["Players"][player_id]["Level"]

    statuses = list(data["Players"][player_id]["ActiveStatuses"].keys())
    statuses_lasting = list(data["Players"][player_id]["ActiveStatuses"].values())

    inventory = []
    for item in data["Players"][player_id]["Inventory"]:
        if item["Name"] == "Kristal života":
            inventory.append(Field.POTION)
        elif item["Name"] == "Freeze scroll":
            inventory.append(Field.FREEZE)
        elif item["Name"] == "Dizzy scroll":
            inventory.append(Field.CONFUSION)

    cards = []
    cooldowns = []
    for card in data["Players"][player_id]["Cards"]:
        if card["Name"] == "Card of Ice Cubes":
            cards.append(Field.MONSTER_CARD_1)
            cooldowns.append(card["Cooldown"] - card["CooldownCounter"])
        elif card["Name"] == "Card of Ice Mage":
            cards.append(Field.MONSTER_CARD_2)
            cooldowns.append(card["Cooldown"] - card["CooldownCounter"])
        elif "card" in card["Name"].lower():
            cards.append(Field.MONSTER_CARD_3)
            cooldowns.append(card["Cooldown"] - card["CooldownCounter"])

    other_key = next(k for k in data["Players"] if k != player_id)
    me_x, me_y = data["Players"][player_id]["Position"]["X"], data["Players"][player_id]["Position"]["Y"]
    opp_x, opp_y = data["Players"][other_key]["Position"]["X"], data["Players"][other_key]["Position"]["Y"]
    map[16 * me_x + me_y] = Field.ME
    map[16 * opp_x + opp_y] = Field.OPPONENT

    return State(player_id, other_key, max_hp, attack_dmg, hp, level, xp, inventory, cards, cooldowns,
                 map, statuses, statuses_lasting, (me_x, me_y), (opp_x, opp_y))


def get_state(url, player_id):
    response = requests.get(url, timeout=5)
    data = response.json() if response.status_code == 200 else None
    if data is None:
        raise Exception("Problem parsing state")
    return parse_state(data, player_id)


def find_my_player_id(game_state, bot_name):
    players = game_state.get('Players', {})
    for _, player in players.items():
        if player.get('Name') == bot_name:
            return player.get('Id')
    return None




MAP_W = 32
MAP_H = 16


def get_possible_moves(state_map, pos, max_stamina=4):
    """
    Vraca sve dostupne pozicije kretanjem u jednom pravcu (gore/dole/levo/desno).
    Sneg kosta 2 staminu po polju, ostalo 1.
    WALL i EMPTY blokiraju kretanje.
    Vraca dict {(x, y): stamina_potrosena}.
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.FREEZE, Field.CONFUSION, Field.POTION,
               Field.MY_MONSTER_1, Field.MY_MONSTER_2, Field.MY_MONSTER_3,
               Field.ENEMY_MONSTER_1, Field.ENEMY_MONSTER_2, Field.ENEMY_MONSTER_3,
               Field.MONSTER_CARD_1, Field.MONSTER_CARD_2, Field.MONSTER_CARD_3,
               Field.OPPONENT}

    x, y = pos
    current_tile = state_map[x * MAP_H + y]
    used_at_start = 1 if current_tile == Field.SNOW else 0

    moves = {}

    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        stamina = used_at_start
        nx, ny = x, y
        while stamina < max_stamina:
            nx += dx
            ny += dy
            if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                break
            tile = state_map[nx * MAP_H + ny]
            if tile in BLOCKED:
                break
            stamina += 2 if tile == Field.SNOW else 1
            if stamina <= max_stamina:
                moves[(nx, ny)] = stamina

    return moves


# Redosled pravaca: LEFT, RIGHT, UP, DOWN — svaki ima max_stamina koraka
# Vektor: [L1,L2,L3,L4, R1,R2,R3,R4, U1,U2,U3,U4, D1,D2,D3,D4]
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

def get_move_vector(state_map, pos, max_stamina=4):
    """
    Vraca numpy array oblika (4 * max_stamina,) = (16,).
    1 = moze da se pomeri na taj korak u tom pravcu, 0 = ne moze.
    Ako je korak N blokiran, koraci N+1..max_stamina su takodje 0.
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.FREEZE, Field.CONFUSION, Field.POTION,
               Field.MY_MONSTER_1, Field.MY_MONSTER_2, Field.MY_MONSTER_3,
               Field.ENEMY_MONSTER_1, Field.ENEMY_MONSTER_2, Field.ENEMY_MONSTER_3,
               Field.MONSTER_CARD_1, Field.MONSTER_CARD_2, Field.MONSTER_CARD_3,
               Field.OPPONENT}

    x, y = pos
    current_tile = state_map[x * MAP_H + y]
    used_at_start = 1 if current_tile == Field.SNOW else 0

    vector = np.zeros(len(DIRECTIONS) * max_stamina, dtype=np.int8)

    for dir_idx, (dx, dy) in enumerate(DIRECTIONS):
        stamina = used_at_start
        nx, ny = x, y
        for step in range(max_stamina):
            nx += dx
            ny += dy
            if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                break
            tile = state_map[nx * MAP_H + ny]
            if tile in BLOCKED:
                break
            stamina += 2 if tile == Field.SNOW else 1
            if stamina <= max_stamina:
                vector[dir_idx * max_stamina + step] = 1
            else:
                break

    return vector


def get_summon_positions(state_map, pos):
    """
    Vraca listu (x, y) pozicija na kojima se moze postaviti monster
    (jedno polje gore/dole/levo/desno, nije blokirano).
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.SPIKES, Field.FREEZE, Field.CONFUSION,
               Field.POTION, Field.MY_MONSTER_1, Field.MY_MONSTER_2, Field.MY_MONSTER_3,
               Field.ENEMY_MONSTER_1, Field.ENEMY_MONSTER_2, Field.ENEMY_MONSTER_3,
               Field.OPPONENT,
               Field.MONSTER_CARD_1, Field.MONSTER_CARD_2, Field.MONSTER_CARD_3}

    x, y = pos
    positions = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            continue
        tile = state_map[nx * MAP_H + ny]
        if tile not in BLOCKED:
            positions.append((nx, ny))
    return positions


def get_summon_vectors(state_map, pos, cards):
    """
    Za svaku karticu koja nije na cooldown-u vraca vektor (4,) int8.
    Redosled: LEFT, RIGHT, UP, DOWN — 1 = moze da postavi, 0 = ne moze.
    Vraca listu [(card, np.array(4,)), ...] — jedan unos po dostupnoj karti.
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.SPIKES, Field.FREEZE, Field.CONFUSION,
               Field.POTION, Field.MY_MONSTER_1, Field.MY_MONSTER_2, Field.MY_MONSTER_3,
               Field.ENEMY_MONSTER_1, Field.ENEMY_MONSTER_2, Field.ENEMY_MONSTER_3,
               Field.OPPONENT,
               Field.MONSTER_CARD_1, Field.MONSTER_CARD_2, Field.MONSTER_CARD_3}

    x, y = pos
    base_vector = np.zeros(len(DIRECTIONS), dtype=np.int8)
    for dir_idx, (dx, dy) in enumerate(DIRECTIONS):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            continue
        tile = state_map[nx * MAP_H + ny]
        if tile not in BLOCKED:
            base_vector[dir_idx] = 1

    result = []
    for card in cards:
        if not card.get("OnCooldown", False):
            result.append((card, base_vector.copy()))

    return result


class Item(Enum):
    POTION = 1
    CONFUSION = 2
    FREEZE = 3

def get_possible_pickups(state, player_pos):
    """
    Vraca dict sa posebnim maskama za svaki pickup i monster card.

    Svaka maska:
    [up, down, left, right]

    1 = respektivni objekat postoji u tom pravcu
    0 = ne postoji
    """

    x, y = player_pos

    directions = [
        (0, 1),   # up
        (0, -1),    # down
        (-1, 0),   # left
        (1, 0)     # right
    ]

    tracked_fields = [
        Field.POTION,
        Field.FREEZE,
        Field.CONFUSION,
        Field.MONSTER_CARD_1,
        Field.MONSTER_CARD_2,
        Field.MONSTER_CARD_3
    ]

    masks = {field: [0, 0, 0, 0] for field in tracked_fields}

    for i, (dx, dy) in enumerate(directions):
        nx, ny = x + dx, y + dy

        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            continue

        tile = state.map[nx * MAP_H + ny]

        if tile in masks:
            masks[tile][i] = 1

    return masks

def flatten_possible_pickups(masks):
    result = []

    ordered_fields = [
        Field.POTION,
        Field.FREEZE,
        Field.CONFUSION,
        Field.MONSTER_CARD_1,
        Field.MONSTER_CARD_2,
        Field.MONSTER_CARD_3
    ]

    for field in ordered_fields:
        result.extend(masks[field])

    return np.array(result, dtype=np.int8)

def get_inventory_vector(inventory):
    """
    Vraca vektor [POTION, FREEZE, CONFUSION]

    1 = imam bar jedan
    0 = nemam
    """

    vector = np.zeros(3, dtype=np.int8)

    if Field.POTION in inventory:
        vector[0] = 1

    if Field.FREEZE in inventory:
        vector[1] = 1

    if Field.CONFUSION in inventory:
        vector[2] = 1

    return vector


_FIELD_CHAR = {
    Field.NORMAL:          " .",
    Field.SNOW:            "~~",
    Field.SPIKES:          "^^",
    Field.WALL:            "##",
    Field.EMPTY:           "  ",
    Field.POTION:          "PO",
    Field.CONFUSION:       "DZ",
    Field.FREEZE:          "FR",
    Field.MY_MONSTER_1:    "M1",
    Field.MY_MONSTER_2:    "M2",
    Field.MY_MONSTER_3:    "M3",
    Field.MONSTER_CARD_1:  "C1",
    Field.MONSTER_CARD_2:  "C2",
    Field.MONSTER_CARD_3:  "C3",
    Field.ME:              "ME",
    Field.OPPONENT:        "OP",
    Field.ENEMY_MONSTER_1: "E1",
    Field.ENEMY_MONSTER_2: "E2",
    Field.ENEMY_MONSTER_3: "E3",
}

def print_map(state_map):
    print("    " + "".join(f"{x:2d}" for x in range(MAP_W)))
    print("    " + "--" * MAP_W)
    for y in range(MAP_H):
        row = f"{y:2d} |"
        for x in range(MAP_W):
            tile = state_map[x * MAP_H + y]
            row += _FIELD_CHAR.get(tile, "??")
        print(row)
    print()


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