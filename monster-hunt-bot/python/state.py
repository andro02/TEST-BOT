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
    def __init__(self, health, level, xp, inventory, cards, monster_cooldowns, map, statuses, statuses_lasting, me_xy, opp_xy):
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
        self.health = health
        self.level = level
        self.xp = xp
        # 1 potion, 2 confusion, 3 freeze
        self.inventory = inventory
        # 1 je monster 1, 2 monster 2, 3 monster 3
        self.cards = cards
        # koliko monstera posedujem 1. pozicija za kolicinu monster 1, 2. pozicija za kolicinu monster 2, 3. pozicija za kolicinu monster 3
        self.monsters = monsters
        # koliko poteza dok ne mogu opet koristim sledeceg monstera
        self.monster_cooldowns = monster_cooldowns
        # kolekcija enuma Field
        self.map = map
        # koji status imam i koliko traje jos
        self.statuses = statuses
        self.statuses_lasting = statuses_lasting
        self.me_xy = me_xy
        self.opp_xy = opp_xy

    def get_state_vector(self):
        state_vector = np.concatenate([
            np.array([
                self.health,
                self.level,
                self.xp
            ]),

            # inventory
            np.array(self.inventory),

            # cards
            np.array(self.cards),

            # monsters
            np.array(self.monsters),

            # cooldowns
            np.array(self.monster_cooldowns),

            # map flattened
            np.array(self.map),

            # statuses
            np.array(self.statuses),

            # statuses lasting
            np.array(self.statuses_lasting),
            np.array(self.me_xy),
            np.array(self.opp_xy)

        ])
        return state_vector

    def inventory_count(self):
        return len(self.inventory)

    def inventory_full(self):
        return self.inventory_count() >= 3

    def add_item(self, item):
        if self.inventory_full():
            return False

        if item == Item.POTION:
            self.inventory.append(Field.POTION)
        elif item == Item.CONFUSION:
            self.inventory.append(Field.CONFUSION)
        elif item == Item.FREEZE:
            self.inventory.append(Field.FREEZE)
        else:
            raise ValueError("Invalid item type")

        return True

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
        elif map_field["MonsterCard"]["Name"] == "Card of Ice Cubes":
            return Field.MONSTER_CARD_2
        elif map_field["MonsterCard"]["Name"] == "Card of Ice Cubes":
            return Field.MONSTER_CARD_3

    if map_field["Entity"] is not None and "Name" in map_field["Entity"] and "SummonedByPlayerId" in map_field["Entity"]:
        if map_field["Entity"]["Name"] == "Ice cube":
            if map_field["Entity"]["SummonedByPlayerId"] == player_id:
                return Field.MY_MONSTER_1
            else:
                return Field.ENEMY_MONSTER_1
        elif map_field["Entity"]["Name"] == "Ice cube":
            if map_field["Entity"]["SummonedByPlayerId"] == player_id:
                return Field.MY_MONSTER_2
            else:
                return Field.ENEMY_MONSTER_2
        elif map_field["Entity"]["Name"] == "Ice cube":
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



def get_state(url, player_id):
    response = requests.get(url, timeout=5)
    data =  response.json() if response.status_code == 200 else None
    if data is None:
        raise Exception("Problem parsing state")

    map = []
    for field in data["Map"]["Grid"]:
        map.append(convertToField(field, player_id))

    hp = data["Players"][player_id]["Health"]
    max_hp = data["Players"][player_id]["MaxHealth"]

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
            cards.append(Field.MONSTER_1)
            cooldowns.append(card["Cooldown"] - card["CooldownCounter"])
        elif card["Name"] == "Card of Ice Cubes":
            cards.append(Field.MONSTER_2)
            cooldowns.append(card["Cooldown"] - card["CooldownCounter"])
        elif card["Name"] == "Card of Ice Cubes":
            cards.append(Field.MONSTER_3)
            cooldowns.append(card["Cooldown"] - card["CooldownCounter"])


    other_key = next(k for k in data["Players"] if k != player_id)
    me_x, me_y = data["Players"][player_id]["Position"]["X"], data["Players"][player_id]["Position"]["Y"]
    opp_x, opp_y = data["Players"][other_key]["Position"]["X"], data["Players"][other_key]["Position"]["Y"]
    map[16 * me_x + me_y] = Field.ME
    map[16 * opp_x + opp_y] = Field.OPPONENT

    print(map)

    return State(hp, level, xp, inventory, cards, cooldowns, map, statuses, statuses_lasting, (me_x, me_y), (opp_x, opp_y))


def find_my_player_id(game_state, bot_name):
    players = game_state.get('Players', {})
    for _, player in players.items():
        if player.get('Name') == bot_name:
            return player.get('Id')
    return None




MAP_W = 32
MAP_H = 16


def get_possible_moves(map_grid, pos, max_stamina=4):
    """
    Vraca sve dostupne pozicije kretanjem u jednom pravcu (gore/dole/levo/desno).
    Sneg kosta 2 staminu po polju, ostalo 1.
    WALL i EMPTY blokiraju kretanje.
    Vraca dict {(x, y): stamina_potrosena}.
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.FREEZE, Field.CONFUSION, Field.POTION, 
               Field.MONSTER_1, Field.MONSTER_2, Field.MONSTER_3,
               Field.MONSTER_CARD_1, Field.MONSTER_CARD_2, Field.MONSTER_CARD_3 }

    current_tile = map_grid.get(pos, Field.NORMAL)
    used_at_start = 1 if current_tile == Field.SNOW else 0

    moves = {}
    x, y = pos

    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        stamina = used_at_start
        nx, ny = x, y
        while stamina < max_stamina:
            nx += dx
            ny += dy
            if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                break
            tile = map_grid.get((nx, ny), Field.NORMAL)
            if tile in BLOCKED:
                break
            stamina += 2 if tile == Field.SNOW else 1
            if stamina <= max_stamina:
                moves[(nx, ny)] = stamina

    return moves


# Redosled pravaca: LEFT, RIGHT, UP, DOWN — svaki ima max_stamina koraka
# Vektor: [L1,L2,L3,L4, R1,R2,R3,R4, U1,U2,U3,U4, D1,D2,D3,D4]
DIRECTIONS = [(-1, 0), (1, 0), (0, -1), (0, 1)]

def get_move_vector(map_grid, pos, max_stamina=4):
    """
    Vraca numpy array oblika (4 * max_stamina,) = (16,).
    1 = moze da se pomeri na taj korak u tom pravcu, 0 = ne moze.
    Ako je korak N blokiran, koraci N+1..max_stamina su takodje 0.
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.FREEZE, Field.CONFUSION, Field.POTION,
               Field.MONSTER_1, Field.MONSTER_2, Field.MONSTER_3,
               Field.MONSTER_CARD_1, Field.MONSTER_CARD_2, Field.MONSTER_CARD_3}

    current_tile = map_grid.get(pos, Field.NORMAL)
    used_at_start = 1 if current_tile == Field.SNOW else 0

    vector = np.zeros(len(DIRECTIONS) * max_stamina, dtype=np.int8)
    x, y = pos

    for dir_idx, (dx, dy) in enumerate(DIRECTIONS):
        stamina = used_at_start
        nx, ny = x, y
        for step in range(max_stamina):
            nx += dx
            ny += dy
            if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
                break
            tile = map_grid.get((nx, ny), Field.NORMAL)
            if tile in BLOCKED:
                break
            stamina += 2 if tile == Field.SNOW else 1
            if stamina <= max_stamina:
                vector[dir_idx * max_stamina + step] = 1
            else:
                break

    return vector


def get_summon_positions(map_grid, pos):
    """
    Vraca listu (x, y) pozicija na kojima se moze postaviti monster
    (jedno polje gore/dole/levo/desno, nije blokirano).
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.SPIKES, Field.FREEZE, Field.CONFUSION,
               Field.POTION, Field.MONSTER_1, Field.MONSTER_2, Field.MONSTER_3, 
               Field.MONSTER_CARD_1, Field.MONSTER_CARD_2, Field.MONSTER_CARD_3 }

    x, y = pos
    positions = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            continue
        tile = map_grid.get((nx, ny), Field.NORMAL)
        if tile not in BLOCKED:
            positions.append((nx, ny))
    return positions


def get_summon_vectors(map_grid, pos, cards):
    """
    Za svaku karticu koja nije na cooldown-u vraca vektor (4,) int8.
    Redosled: LEFT, RIGHT, UP, DOWN — 1 = moze da postavi, 0 = ne moze.
    Vraca listu [(card, np.array(4,)), ...] — jedan unos po dostupnoj karti.
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.SPIKES, Field.FREEZE, Field.CONFUSION,
               Field.POTION, Field.MONSTER_1, Field.MONSTER_2, Field.MONSTER_3,
               Field.MONSTER_CARD_1, Field.MONSTER_CARD_2, Field.MONSTER_CARD_3}

    x, y = pos
    base_vector = np.zeros(len(DIRECTIONS), dtype=np.int8)
    for dir_idx, (dx, dy) in enumerate(DIRECTIONS):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            continue
        tile = map_grid.get((nx, ny), Field.NORMAL)
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


def get_adjacent_pickups(state, pos):
    if state.inventory_full():
        return []

    x, y = pos
    pickups = []

    directions = [
        (0, -1),  # up
        (0, 1),  # down
        (-1, 0),  # left
        (1, 0)  # right
    ]

    for dx, dy in directions:
        nx, ny = x + dx, y + dy

        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            continue

        tile = state.map.get((nx, ny), Field.NORMAL)

        if tile == Field.POTION:
            pickups.append(((nx, ny), Item.POTION))
        elif tile == Field.FREEZE:
            pickups.append(((nx, ny), Item.FREEZE))
        elif tile == Field.CONFUSION:
            pickups.append(((nx, ny), Item.CONFUSION))

    return pickups


def pickup_item_at(state, player_pos, target_pos):
    legal_pickups = get_adjacent_pickups(state, player_pos)

    for pos, item in legal_pickups:
        if pos == target_pos:

            success = state.add_item(item)

            if success:
                state.map[pos] = Field.NORMAL
                return True

    return False


def get_pickup_mask(state, player_pos):
    if state.inventory_full():
        return [0, 0, 0, 0]

    x, y = player_pos

    directions = [
        (0, -1),  # up
        (0, 1),  # down
        (-1, 0),  # left
        (1, 0)  # right
    ]

    item_tiles = {
        Field.POTION,
        Field.FREEZE,
        Field.CONFUSION
    }

    mask = []

    for dx, dy in directions:
        nx, ny = x + dx, y + dy

        if not (0 <= nx < MAP_W and 0 <= ny < MAP_H):
            mask.append(0)
            continue

        tile = state.map.get((nx, ny), Field.NORMAL)

        if tile in item_tiles:
            mask.append(1)
        else:
            mask.append(0)

    return mask


if __name__ == "__main__":
    url = "http://localhost:8080"
    game_id = "a70eec86-9fae-4f25-8ad4-84357d435578"
    bot_name = "dsa"

    response = requests.get(f"{url}/game/state/{game_id}", timeout=5)
    data = response.json() if response.status_code == 200 else None
    if data is None:
        raise Exception("Problem parsing state")

    # Napravi map_grid dict
    map_grid = {}
    for field in data["Map"]["Grid"]:
        pos = field["Position"]
        x, y = pos["X"], pos["Y"]
        tile = convertToField(field)
        map_grid[(x, y)] = tile if tile is not None else Field.NORMAL

    player_id = find_my_player_id(data, bot_name)
    if player_id is None:
        raise Exception(f"Igrac '{bot_name}' nije nadjen")

    player = data["Players"][str(player_id)]
    state = get_state(f"{url}/game/state/{game_id}", str(player_id))

    # state.map iz get_state je trenutno lista, pickup hoce dict
    state.map = map_grid
    my_pos = (player["Position"]["X"], player["Position"]["Y"])
    print(f"Igrac '{bot_name}' ID={player_id} na poziciji {my_pos}")

    # Moguca kretanja
    moves = get_possible_moves(map_grid, my_pos)
    print(f"\nMoguca kretanja ({len(moves)}):")
    for dest, cost in sorted(moves.items()):
        tile = map_grid.get(dest, Field.NORMAL)
        print(f"  X={dest[0]}  Y={dest[1]}  stamina={cost}  tile={tile.name}")

    print(get_move_vector(map_grid, my_pos))

    # Moguce pozicije za summon
    cards = player.get("Cards") or []
    summon_vecs = get_summon_vectors(map_grid, my_pos, cards)

    if summon_vecs:
        for i, (card, vector) in enumerate(summon_vecs):
            card_name = card.get("Name", "?")
            card_id = card.get("Id", "?")
            true_positions = [(x, y) for x in range(MAP_W) for y in range(MAP_H) if vector[x * MAP_H + y]]
            print(f"\nKarta [{i}] '{card_name}' (ID={card_id}) — True={vector.sum()} pozicija:")
            for (sx, sy) in true_positions:
                tile = map_grid.get((sx, sy), Field.NORMAL)
                print(f"  X={sx}  Y={sy}  tile={tile.name}")
    else:
        print("\nNema dostupnih karata za postavljanje")

    # Pickup logika

    pickup_mask = get_pickup_mask(state, my_pos)
    print(f"\nPickup mask [up, down, left, right]: {pickup_mask}")

    pickups = get_adjacent_pickups(state, my_pos)

    if pickups:
        print("\nMoguci pickup itemi:")
        for item_pos, item in pickups:
            print(f"  {item_pos} -> {item.name}")

        target_pos, target_item = pickups[0]

        success = pickup_item_at(state, my_pos, target_pos)

        if success:
            print(f"\nPickup uspesan: {target_item.name} sa polja {target_pos}")
        else:
            print(f"\nPickup neuspesan: {target_item.name} sa polja {target_pos}")

    else:
        print("\nNema legalnih pickup itema.")

    print("\nInventory stanje:")
    print(state.inventory)

    print(f"\nUkupno itema: {state.inventory_count()}")
    print(f"Inventory full: {state.inventory_full()}")