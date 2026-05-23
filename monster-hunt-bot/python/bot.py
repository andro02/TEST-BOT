"""Monster Hunt Bot - Strategic implementation
Usage: python bot.py <server_url> <game_id> <bot_name>
"""
import requests
import sys
import time
from collections import deque

# FieldType: 0=BASE, 1=NORMAL, 2=OBSTACLE_SLOW, 3=OBSTACLE(damage), 4=POWERUP, 5=WALL, 6=EMPTY
WALKABLE_FIELD_TYPES = {0, 1, 2, 4, 6}


class MonsterHuntBot:
    def __init__(self, server_url, game_id, bot_name):
        self.server_url = server_url.rstrip('/')
        self.game_id = game_id
        self.bot_name = bot_name
        self.player_id = None

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def get_game_state(self):
        url = f"{self.server_url}/game/state/{self.game_id}"
        try:
            r = requests.get(url, timeout=5)
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            print(f"  [get_state error] {e}")
            return None

    def _put(self, path, payload=None):
        url = f"{self.server_url}{path}"
        try:
            r = requests.put(url, json=payload, timeout=5)
            if r.status_code == 200:
                return r.json()
            print(f"  [PUT {path}] {r.status_code}: {r.text[:120]}")
        except Exception as e:
            print(f"  [PUT error] {e}")
        return None

    def move(self, new_pos):
        return self._put(
            f"/player/move/gameId/{self.game_id}",
            {"playerId": self.player_id, "newPosition": {"X": new_pos[0], "Y": new_pos[1]}},
        )

    def attack(self, target_id):
        return self._put(f"/player/{self.player_id}/attack/{target_id}/gameId/{self.game_id}")

    def use_item(self, item_id):
        return self._put(f"/player/{self.player_id}/use-item/{item_id}/gameId/{self.game_id}")

    def pickup(self, pos):
        return self._put(
            f"/map/pickup/{self.player_id}/gameId/{self.game_id}",
            {"Position": {"X": pos[0], "Y": pos[1]}},
        )

    def summon(self, card_id, pos):
        return self._put(
            f"/map/{self.player_id}/summon/{card_id}/gameId/{self.game_id}",
            {"X": pos[0], "Y": pos[1]},
        )

    # ── State helpers ─────────────────────────────────────────────────────────

    def find_my_player(self, state):
        for cell in state.get('map', {}).get('Grid', []):
            e = cell.get('Entity')
            if e and e.get('Name') == self.bot_name:
                self.player_id = e['Id']
                return e
        for _, p in state.get('Players', {}).items():
            if p.get('Name') == self.bot_name:
                self.player_id = p['Id']
                return p
        return None

    def is_my_turn(self, state):
        if not state or not self.player_id:
            return False
        gs = state.get('GameState', '')
        # Check Players dict first — First flag is more reliably set there
        for p in state.get('Players', {}).values():
            if p.get('Id') == self.player_id:
                is_first = p.get('First', False)
                result = (is_first and gs == 'Player1Turn') or (not is_first and gs == 'Player2Turn')
                return result
        # Fallback: search Grid entities
        for cell in state.get('map', {}).get('Grid', []):
            e = cell.get('Entity')
            if e and e.get('Id') == self.player_id:
                is_first = e.get('First', False)
                return (is_first and gs == 'Player1Turn') or (not is_first and gs == 'Player2Turn')
        return False

    def is_game_over(self, state):
        return bool(state) and state.get('GameState', '') == 'Ending'

    # ── Map analysis ──────────────────────────────────────────────────────────

    def parse_map(self, state):
        """Return (grid_map, map_w, map_h, my_player, my_pos, enemies, enemy_monsters, items, cards)"""
        m = state.get('map', {})
        map_w = m.get('X', 32)
        map_h = m.get('Y', 16)

        grid_map = {}
        my_player = None
        my_pos = None
        enemies = []        # [(x, y, entity)]
        enemy_monsters = [] # [(x, y, entity)]
        items = []          # [(x, y, item)]
        cards = []          # [(x, y, card)]

        for cell in m.get('Grid', []):
            pos = cell['Position']
            x, y = pos['X'], pos['Y']
            grid_map[(x, y)] = cell

            e = cell.get('Entity')
            if e:
                summoned_by = e.get('SummonedByPlayerId')
                if e.get('Id') == self.player_id:
                    my_player = e
                    my_pos = (x, y)
                elif summoned_by is not None and summoned_by != self.player_id:
                    enemy_monsters.append((x, y, e))
                elif summoned_by is None and e.get('Name') != self.bot_name:
                    enemies.append((x, y, e))

            if cell.get('Item'):
                items.append((x, y, cell['Item']))
            if cell.get('MonsterCard'):
                cards.append((x, y, cell['MonsterCard']))

        return grid_map, map_w, map_h, my_player, my_pos, enemies, enemy_monsters, items, cards

    # ── Pathfinding ───────────────────────────────────────────────────────────

    def get_reachable_cells(self, start, max_steps, grid_map, map_w, map_h):
        """BFS — returns set of all empty cells reachable from start within max_steps moves."""
        reachable = set()
        queue = deque([(start, 0)])
        visited = {start}
        while queue:
            pos, steps = queue.popleft()
            if pos != start:
                reachable.add(pos)
            if steps >= max_steps:
                continue
            x, y = pos
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                np_ = (nx, ny)
                if np_ in visited or not (0 <= nx < map_w and 0 <= ny < map_h):
                    continue
                cell = grid_map.get(np_)
                if not cell or cell.get('FieldType', 1) not in WALKABLE_FIELD_TYPES or cell.get('Entity'):
                    continue
                visited.add(np_)
                queue.append((np_, steps + 1))
        return reachable

    def bfs_path(self, start, target, grid_map, map_w, map_h):
        """BFS from start to target. Returns full path list or None."""
        if start == target:
            return [start]
        queue = deque([(start, [start])])
        visited = {start}
        while queue:
            pos, path = queue.popleft()
            x, y = pos
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                np_ = (nx, ny)
                if np_ in visited or not (0 <= nx < map_w and 0 <= ny < map_h):
                    continue
                cell = grid_map.get(np_)
                if not cell:
                    continue
                visited.add(np_)
                new_path = path + [np_]
                if np_ == target:
                    return new_path
                if cell.get('FieldType', 1) in WALKABLE_FIELD_TYPES and not cell.get('Entity'):
                    queue.append((np_, new_path))
        return None

    @staticmethod
    def manhattan(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    # ── Move scoring ──────────────────────────────────────────────────────────

    def _score_move(self, dest, enemies, enemy_monsters, items, cards,
                    hp, max_hp, atk_range, grid_map, map_w, map_h):
        score = 0

        # Closing in on enemy players
        if enemies:
            min_dist = min(self.manhattan(dest, (ex, ey)) for ex, ey, _ in enemies)
            score += max(0, 80 - min_dist * 8)
            if min_dist <= atk_range:
                score += 300  # will be able to attack next action

        # Closing in on enemy monsters
        if enemy_monsters:
            min_dist = min(self.manhattan(dest, (mx, my_)) for mx, my_, _ in enemy_monsters)
            score += max(0, 50 - min_dist * 6)
            if min_dist <= atk_range:
                score += 150

        # Moving toward health crystals when hurt
        for ix, iy, item in items:
            if item.get('ItemType') == 1 and hp < max_hp * 0.7:
                dist = self.manhattan(dest, (ix, iy))
                urgency = 3 if hp < max_hp * 0.4 else 1
                score += max(0, (40 - dist * 5)) * urgency

        # Moving toward monster cards on the map
        for cx, cy, _ in cards:
            dist = self.manhattan(dest, (cx, cy))
            score += max(0, 30 - dist * 4)

        # Small penalty for slow tiles
        if grid_map.get(dest, {}).get('FieldType') == 2:
            score -= 15

        # Tiny nudge toward map center when nothing else matters
        if score == 0:
            score -= self.manhattan(dest, (map_w // 2, map_h // 2))

        return score

    # ── Action enumeration ────────────────────────────────────────────────────

    def get_possible_actions(self, state):
        """Return sorted list of (score, action_type, params, description) for every legal action."""
        grid_map, map_w, map_h, my_player, my_pos, enemies, enemy_monsters, items, cards = self.parse_map(state)
        if not my_player or not my_pos:
            return []

        hp        = my_player.get('Health', 100)
        max_hp    = my_player.get('MaxHealth', 100)
        atk       = my_player.get('AttackPower', 25)
        atk_range = my_player.get('AttackRange', 1)
        max_move  = my_player.get('MaxMoveDistance', 4)
        inventory = my_player.get('Inventory', []) or []
        my_cards  = my_player.get('Cards', []) or []

        actions = []  # (score, type, params, description)

        # ── Attack enemy players ──
        for ex, ey, enemy in enemies:
            if self.manhattan(my_pos, (ex, ey)) <= atk_range:
                e_hp  = enemy.get('Health', 100)
                kills = atk >= e_hp
                score = 2000 + (500 if kills else 0)
                actions.append((score, 'attack', enemy['Id'],
                                f"Attack player '{enemy.get('Name')}' HP={e_hp}/{enemy.get('MaxHealth',100)} {'★KILL' if kills else ''}"))

        # ── Attack enemy monsters ──
        for mx, my_, monster in enemy_monsters:
            if self.manhattan(my_pos, (mx, my_)) <= atk_range:
                m_hp  = monster.get('Health', 100)
                kills = atk >= m_hp
                score = 1200 + (300 if kills else 0)
                actions.append((score, 'attack', monster['Id'],
                                f"Attack monster HP={m_hp}/{monster.get('MaxHealth',100)} at ({mx},{my_}) {'★KILL' if kills else ''}"))

        # ── Use items from inventory ──
        for item in inventory:
            itype = item.get('ItemType')
            if itype == 1:  # health crystal
                missing = max_hp - hp
                if hp < max_hp * 0.7:
                    score = int(missing / max_hp * 1800)
                    actions.append((score, 'use_item', item['Id'],
                                   f"Use '{item.get('Name','heal')}' (+{item.get('Power',50)}% HP, missing {missing})"))
            elif itype == 5:  # freeze scroll
                if enemies:
                    closest = min(self.manhattan(my_pos, (ex, ey)) for ex, ey, _ in enemies)
                    score = 1100 if closest <= 2 else (600 if closest <= 4 else 200)
                    actions.append((score, 'use_item', item['Id'],
                                   f"Use freeze scroll (closest enemy dist={closest})"))

        # ── Pickup at current cell ──
        cur_cell = grid_map.get(my_pos, {})
        if cur_cell.get('MonsterCard'):
            card_name = cur_cell['MonsterCard'].get('Name', 'monster card')
            actions.append((1000, 'pickup', my_pos, f"Pick up card '{card_name}' at {my_pos}"))
        if cur_cell.get('Item'):
            item_name = cur_cell['Item'].get('Name', 'item')
            actions.append((900, 'pickup', my_pos, f"Pick up '{item_name}' at {my_pos}"))

        # ── Summon monster ──
        if my_cards:
            closest_enemy_dist = min(
                (self.manhattan(my_pos, (ex, ey)) for ex, ey, _ in enemies), default=999
            )
            for card in my_cards:
                if card.get('OnCooldown', False):
                    continue
                m = card.get('Monster', {})
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    sx, sy = my_pos[0] + dx, my_pos[1] + dy
                    sc = grid_map.get((sx, sy))
                    if sc and sc.get('FieldType', 1) in WALKABLE_FIELD_TYPES and not sc.get('Entity'):
                        score = 800 if closest_enemy_dist <= max_move + 2 else 300
                        actions.append((score, 'summon', (card['Id'], (sx, sy)),
                                       f"Summon '{card.get('Name','?')}' "
                                       f"HP={m.get('Health','?')} ATK={m.get('AttackPower','?')} "
                                       f"RNG={m.get('AttackRange','?')} at ({sx},{sy})"))
                        break  # one position per card is enough

        # ── Move actions ──
        reachable = self.get_reachable_cells(my_pos, max_move, grid_map, map_w, map_h)
        for dest in reachable:
            score = self._score_move(dest, enemies, enemy_monsters, items, cards,
                                     hp, max_hp, atk_range, grid_map, map_w, map_h)
            actions.append((score, 'move', dest, f"Move to {dest}"))

        actions.sort(key=lambda a: -a[0])
        return actions

    # ── Main turn logic ───────────────────────────────────────────────────────

    def take_turn(self, state):
        _, _, _, my_player, my_pos, enemies, enemy_monsters, items, cards = self.parse_map(state)
        if not my_player or not my_pos:
            return state

        hp       = my_player.get('Health', 100)
        max_hp   = my_player.get('MaxHealth', 100)
        my_cards = my_player.get('Cards', []) or []
        inventory = my_player.get('Inventory', []) or []

        print(f"  Pos={my_pos}  HP={hp}/{max_hp}  Cards={len(my_cards)}  Inv={len(inventory)}")
        print(f"  Enemies={len(enemies)}  EnemyMonsters={len(enemy_monsters)}  "
              f"Items_on_map={len(items)}  Cards_on_map={len(cards)}")

        actions = self.get_possible_actions(state)

        move_count  = sum(1 for a in actions if a[1] == 'move')
        other_count = len(actions) - move_count
        print(f"  === {len(actions)} possible actions ({move_count} moves, {other_count} other) ===")
        for i, (score, atype, params, desc) in enumerate(actions[:10]):
            marker = "=>" if i == 0 else "  "
            print(f"    {marker} [{i+1}] {atype:10s} score={score:5d}  {desc}")
        if len(actions) > 10:
            print(f"       ... and {len(actions) - 10} more move options")

        if not actions:
            print("  No actions available — skipping turn")
            return state

        _, atype, params, desc = actions[0]
        print(f"  Executing: {desc}")

        if atype == 'attack':
            return self.attack(params) or state
        elif atype == 'use_item':
            return self.use_item(params) or state
        elif atype == 'pickup':
            return self.pickup(params) or state
        elif atype == 'summon':
            card_id, pos = params
            return self.summon(card_id, pos) or state
        elif atype == 'move':
            return self.move(params) or state

        return state


# ── Entry point ───────────────────────────────────────────────────────────────

def start_game(server_url, bot_name, bot2_name="Bot2"):
    url = f"{server_url}/game/start/names?player1Name={bot_name}&player2Name={bot2_name}"
    try:
        r = requests.get(url, timeout=5)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"Start game error: {e}")
        return None


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python bot.py <server_url> <game_id> <bot_name>")
        sys.exit(1)

    server_url = sys.argv[1]
    bot_name   = sys.argv[3]
    bot2_name  = sys.argv[4] if len(sys.argv) > 4 else "Bot2"

    game_data = start_game(server_url, bot_name, bot2_name)
    if not game_data:
        print("Failed to start game")
        sys.exit(1)

    game_id = game_data["gameId"]
    print(f"Game started: {game_id}")

    bot1 = MonsterHuntBot(server_url, game_id, bot_name)
    bot2 = MonsterHuntBot(server_url, game_id, bot2_name)

    state = None
    print("Waiting for game state...")
    while not state or not bot1.find_my_player(state):
        time.sleep(0.5)
        state = bot1.get_game_state()
    bot2.find_my_player(state)

    print(f"Bot1 ID={bot1.player_id}  Bot2 ID={bot2.player_id}")

    try:
        while state and not bot1.is_game_over(state):
            gs = state.get('GameState', '?')
            t1 = bot1.is_my_turn(state)
            t2 = bot2.is_my_turn(state)
            print(f"  GameState={gs}  bot1_turn={t1}  bot2_turn={t2}")
            if t1:
                print(f"\n[BOT1] GameState={gs}")
                bot1.take_turn(state)
                state = bot1.get_game_state() or state
            elif t2:
                print(f"\n[BOT2] GameState={gs}")
                bot2.take_turn(state)
                state = bot1.get_game_state() or state
            else:
                time.sleep(0.3)
                state = bot1.get_game_state()
    except KeyboardInterrupt:
        print("\nBot stopped")
