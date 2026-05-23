import numpy as np

from enum import Enum

import requests

from enum import Enum, auto

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

def convertToField(map_field):

    if map_field["Item"] is not None and map_field["Item"]["Name"] is not None:
        if map_field["Item"]["Name"] == "Kristal života":
            return Field.POTION
        elif map_field["Item"]["Name"] == "Freeze scroll":
            return Field.FREEZE
        elif map_field["Item"]["Name"] == "Dizzy scroll":
            return Field.CONFUSION

    if map_field["MonsterCard"] is not None:
        if map_field["MonsterCard"]["Name"] == "Card of Ice Cubes":
            return Field.MONSTER_1
        elif map_field["MonsterCard"]["Name"] == "Card of Ice Cubes":
            return Field.MONSTER_2
        elif map_field["MonsterCard"]["Name"] == "Card of Ice Cubes":
            return Field.MONSTER_3
        
    if map_field["FieldType"]  == TileType.NORMAL.value:
        return Field.NORMAL
    elif map_field["FieldType"]  == TileType.OBSTACLE_SLOW.value:
        return Field.SNOW
    elif map_field["FieldType"]  == TileType.OBSTACLE.value:
        return Field.SPIKES
    elif map_field["FieldType"]  == TileType.WALL.value:
        return Field.WALL
    elif map_field["FieldType"] == TileType.EMPTY.value:
        return Field.EMPTY


    if map_field["FieldType"] == TileType.BASE or map_field["FieldType"]  == TileType.NORMAL:
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
    MONSTER_1 = 9
    MONSTER_2 = 10
    MONSTER_3 = 11
#   MONSTER CARDS
    MONSTER_CARD_1 = 12
    MONSTER_CARD_2 = 13
    MONSTER_CARD_3 = 14
#   PLAYERS
    ME = 15
    OPPONENT = 16

class State(object):
    def __init__(self, health, level, xp, inventory, cards, monsters, monster_cooldowns, map, statuses, statuses_lasting):
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


def get_state(url, player_id):
    response = requests.get(url, timeout=5)
    data =  response.json() if response.status_code == 200 else None
    if data is None:
        raise Exception("Problem parsing state")

    map = []
    for field in data["Map"]["Grid"]:
        map.append(convertToField(field))

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

    monster1 = 0
    monster2 = 0
    monster3 = 0
    for field in data["Map"]["Grid"]:
        if field["Entity"] is not None and "Name" in field["Entity"] and "SummonedByPlayerId" in field["Entity"]:
            if field["Entity"]["Name"] == "Card of Ice Cubes" and field["Entity"]["SummonedByPlayerId"] == player_id:
                monster1 += 1
            if field["Entity"]["Name"] == "Card of Ice Cubes" and field["Entity"]["SummonedByPlayerId"] == player_id:
                monster2 += 1
            if field["Entity"]["Name"] == "Card of Ice Cubes" and field["Entity"]["SummonedByPlayerId"] == player_id:
                monster3 += 1
    monsters_count = [monster1, monster2, monster3]


    other_key = next(k for k in data["Players"] if k != player_id)
    me_x, me_y = data["Players"][player_id]["X"], data["Players"][player_id]["Y"]
    opp_x, opp_y = data["Players"][other_key]["X"], data["Players"][other_key]["Y"]
    map[32 * me_x + me_y] = Field.ME
    map[32 * opp_x + opp_y] = Field.OPPONENT



    print(map)

    # TODO handle width height

    return State(hp, level, xp, inventory, cards, monsters_count, cooldowns, map, statuses, statuses_lasting)

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


def get_move_vector(map_grid, pos, max_stamina=4):
    """
    Vraca numpy array oblika (32*16,) sa True na poljima gde igrac moze da se pomeri.
    Indeks polja = x * MAP_H + y
    """
    moves = get_possible_moves(map_grid, pos, max_stamina)
    vector = np.zeros(MAP_W * MAP_H, dtype=bool)
    for (x, y) in moves:
        vector[x * MAP_H + y] = True
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
    Za svaku karticu iz inventory-a koja nije na cooldown-u vraca vektor (512,) bool.
    Vraca listu [(card, np.array(512, bool)), ...] — jedan unos po dostupnoj karti.
    """
    positions = get_summon_positions(map_grid, pos)

    base_vector = np.zeros(MAP_W * MAP_H, dtype=bool)
    for (x, y) in positions:
        base_vector[x * MAP_H + y] = True

    result = []
    for card in cards:
        if not card.get("OnCooldown", False):
            result.append((card, base_vector.copy()))

    return result

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
    my_pos = (player["Position"]["X"], player["Position"]["Y"])
    print(f"Igrac '{bot_name}' ID={player_id} na poziciji {my_pos}")

    # Moguca kretanja
    moves = get_possible_moves(map_grid, my_pos)
    print(f"\nMoguca kretanja ({len(moves)}):")
    for dest, cost in sorted(moves.items()):
        tile = map_grid.get(dest, Field.NORMAL)
        print(f"  X={dest[0]}  Y={dest[1]}  stamina={cost}  tile={tile.name}")

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