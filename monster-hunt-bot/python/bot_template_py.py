"""Monster Hunt Bot - Python Template
Usage: python bot_template.py <server_url> <game_id> <bot_name>
See README.md for full API documentation
"""
import requests
import sys
import time

class BotTemplate:
    def __init__(self, server_url, game_id, bot_name):
        self.server_url = server_url.rstrip('/')
        self.game_id = game_id
        self.bot_name = bot_name
        self.player_id = None
    
    def get_game_state(self):
        url = f"{self.server_url}/game/state/{self.game_id}"
        response = requests.get(url, timeout=5)
        return response.json() if response.status_code == 200 else None
    
    def find_my_player_id(self, game_state):
        players = game_state.get('Players', {})
        for player_id, player in players.items():
            if player.get('Name') == self.bot_name:
                self.player_id = player.get('Id')
                return True
        return False
    
    def is_my_turn(self, game_state):
        if not game_state or not self.player_id:
            return False
        players = game_state.get('Players', {})
        my_player = players.get(str(self.player_id)) or players.get(self.player_id)
        if not my_player:
            return False
        is_first = my_player.get('First', False)
        game_state_str = game_state.get('GameState', '')
        print(game_state_str, is_first)
        return (is_first and game_state_str == 'Player1Turn') or (not is_first and game_state_str == 'Player2Turn')
    
    def is_game_over(self, game_state):
        """Check if game has ended"""
        if not game_state:
            return False
        return game_state.get('GameState', '') == 'Ending'
    
    def put_player(self):
        url = f"{self.server_url}/player/move/gameId/{self.game_id}"
        payload = {"playerId": 1, "newPosition": {"x": 5, "y": 7}}  
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(data)
        else:
            print(f"Failed to join game: {response.status_code} - {response.text}")
            return False
        
def start_game(server_url, bot_name):
    url = f"{server_url}/game/start/names?player1Name={bot_name}&player2Name=AI"
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
    bot_name = sys.argv[3]

    game_data = start_game(server_url, bot_name)
    if not game_data:
        print("Failed to start game")
        sys.exit(1)

    game_id = game_data["gameId"]
    print(f"Game started: {game_id}")

    bot = BotTemplate(server_url, game_id, bot_name)

    state = None
    print("Waiting for game state...")
    while not state or not bot.find_my_player_id(state):
        time.sleep(0.5)
        state = bot.get_game_state()

    print(f"Connected as player ID {bot.player_id}")

    try:
        while state and not bot.is_game_over(state):
            print(bot.is_my_turn(state))
            if bot.is_my_turn(state):
                print(f"\nTurn — GameState={state.get('GameState')}")
                new_state = bot.take_turn(state)
                state = new_state if new_state else state
            else:
                time.sleep(0.3)
                state = bot.get_game_state()
    except KeyboardInterrupt:
        print("\nBot stopped")
