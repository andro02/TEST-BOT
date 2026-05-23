import numpy as np
import requests
from enum import Enum


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
            return Field.MONSTER_1
        elif map_field["MonsterCard"]["Name"] == "Card of Ice Cubes":
            return Field.MONSTER_1
        
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

class State(object):
    def __init__(self):
        self.health = 100
        self.level = 0
        self.xp = 0
        # 1 potion, 2 confusion, 3 freeze
        self.inventory = [1, 2, 3]
        # 1 je monster 1, 2 monster 2, 3 monster 3
        self.cards = [1, 2, 3]
        # koliko monstera posedujem 1. pozicija za kolicinu monster 1, 2. pozicija za kolicinu monster 2, 3. pozicija za kolicinu monster 3
        self.monsters = [1, 2, 3]
        # koliko poteza dok ne mogu opet koristim sledeceg monstera
        self.monster_cooldowns = [1, 2, 3]
        # kolekcija enuma Field
        self.map = np.zeros((32, 16))
        # koji status imam i koliko traje jos
        self.status = [1, 2]

MAP_W = 32
MAP_H = 16

def get_possible_moves(map_grid, pos, max_stamina=4):
    """
    Vraca sve dostupne pozicije kretanjem u jednom pravcu (gore/dole/levo/desno).
    Sneg kosta 2 staminu po polju, ostalo 1.
    WALL i EMPTY blokiraju kretanje.
    Vraca dict {(x, y): stamina_potrosena}.
    """
    BLOCKED = {Field.WALL, Field.EMPTY, Field.FREEZE, Field.CONFUSION, Field.POTION, Field.MONSTER_1, Field.MONSTER_2, Field.MONSTER_3 }

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
               Field.POTION, Field.MONSTER_1, Field.MONSTER_2, Field.MONSTER_3}

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
    Vraca dict {card_id: np.array(512, bool)}.
    """
    positions = get_summon_positions(map_grid, pos)

    base_vector = np.zeros(MAP_W * MAP_H, dtype=bool)
    for (x, y) in positions:
        base_vector[x * MAP_H + y] = True

    result = {}
    for card in cards:
        if not card.get("OnCooldown", False):
            result[card["Id"]] = base_vector.copy()

    return result


def get_state(url, game_id):
    url = f"{url}/game/state/{game_id}"
    response = requests.get(url, timeout=5)
    data = response.json() if response.status_code == 200 else None
    if data is None:
        raise Exception("Problem parsing state")

    state = State()
    state.map = {}

    for field in data["Map"]["Grid"]:
        pos = field["Position"]
        x, y = pos["X"], pos["Y"]
        tile = convertToField(field)
        state.map[(x, y)] = tile if tile is not None else Field.NORMAL

    return state, data


if __name__ == "__main__":
    url = "http://localhost:8080"
    game_id = "8339a17b-7b27-489b-9746-2ca203ab6849"
    state, data = get_state(url, game_id)

    # Uzmi poziciju prvog igraca
    players = data.get("Players", {})
    for pid, player in players.items():
        pos = player["Position"]
        my_pos = (pos["X"], pos["Y"])
        name = player["Name"]
        moves = get_possible_moves(state.map, my_pos)
        print(f"\nIgrac '{name}' na {my_pos} — {len(moves)} mogucih poteza:")
        for dest, cost in sorted(moves.items()):
            tile = state.map.get(dest, Field.NORMAL)
            print(f"  {dest}  stamina: {cost}  tile: {tile.name}")

        vector = get_move_vector(state.map, my_pos)
        # print(f"\nVektor kretanja (True={vector.sum()} polja):")
        # print(vector)

        cards = player.get("Cards") or []
        available_cards = [c for c in cards if not c.get("OnCooldown", False)]
        if available_cards:
            summon_pos = get_summon_positions(state.map, my_pos)
            print(f"\nMoguce pozicije za postavljanje monstera ({len(summon_pos)}):")
            for (sx, sy) in summon_pos:
                tile = state.map.get((sx, sy), Field.NORMAL)
                print(f"  X={sx}  Y={sy}  tile={tile.name}")
        else:
            print(f"\nNema dostupnih karata za postavljanje")

