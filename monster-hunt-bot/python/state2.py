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
        if field["Entity"] is not None:
            if field["Entity"]["Name"] == "Card of Ice Cubes" and field["Entity"]["SummonedByPlayerId"] == player_id:
                monster1 += 1
            if field["Entity"]["Name"] == "Card of Ice Cubes"  and field["Entity"]["SummonedByPlayerId"] == player_id:
                monster2 += 1
            if field["Entity"]["Name"] == "Card of Ice Cubes"  and field["Entity"]["SummonedByPlayerId"] == player_id:
                monster3 += 1
    monsters_count = [monster1, monster2, monster3]

    print(map)

    # TODO handle width height

    return State(hp, level, xp, inventory, cards, monsters_count, cooldowns, map, statuses, statuses_lasting)

def find_my_player_id(game_state, bot_name):
    players = game_state.get('Players', {})
    for _, player in players.items():
        if player.get('Name') == bot_name:
            return player.get('Id')
    return None

if __name__ == "__main__":
    url = "http://localhost:8080"
    game_id = "e7fc0306-e1c6-4829-af35-2e4a7394193a"
    url = f"{url}/game/state/{game_id}"
    response = requests.get(url, timeout=5)
    data = response.json() if response.status_code == 200 else None
    if data is None:
        raise Exception("Problem parsing state")
    bot_name = ""
    player_id = find_my_player_id(data, bot_name)
    state = get_state(url, player_id)