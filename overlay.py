import asyncio
import os
import re
import threading
import time
import glob
import csv
import json
from http.server import SimpleHTTPRequestHandler, HTTPServer
import websockets

# === LOAD CONFIG ===
CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError("Missing config.json file. Please create one with log_dir, port, and ws_port values.")

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

LOG_DIR = config.get("log_dir", "H:/P99/Logs")
PORT = config.get("port", 8000)
WS_PORT = config.get("ws_port", 6789)

# === STATIC CONFIG ===
ITEMS_CSV = "items_min.csv"
ITEM_ICON_BASE_URL = "https://raw.githubusercontent.com/nullservices/eqitemicons/refs/heads/main/itemicons"

connected_clients = set()
item_icon_map = {}
main_loop = asyncio.new_event_loop()
asyncio.set_event_loop(main_loop)

# === STATS TRACKING ===
total_deaths = 0
session_deaths = 0
total_kills = 0
session_kills = 0

def reset_session_stats():
    global session_deaths, session_kills
    session_deaths = 0
    session_kills = 0

def send_stats_update():
    send_to_clients({
        "type": "stats",
        "total_deaths": total_deaths,
        "session_deaths": session_deaths,
        "total_kills": total_kills,
        "session_kills": session_kills
    })

# === LOAD ITEM ICONS FROM CSV ===
def load_item_icons():
    try:
        with open(ITEMS_CSV, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile, delimiter='|')
            for row in reader:
                name = re.sub(r"[^a-z0-9 ]", "", row['name'].strip().lower())
                icon = row['icon'].strip()
                if name and icon:
                    item_icon_map[name] = icon
        print(f"[INFO] Loaded {len(item_icon_map)} items from {ITEMS_CSV}")
    except Exception as e:
        print(f"[ERROR] Failed to load {ITEMS_CSV}: {e}")

# === UTILITIES ===
def extract_character_name(log_file):
    filename = os.path.basename(log_file)
    parts = filename.split("_")
    return parts[1] if len(parts) >= 2 else "Unknown"

def extract_current_zone_from_lines(lines):
    for line in reversed(lines):
        match = re.search(r"You have entered (.+?)\.", line)
        if match:
            return match.group(1)
    return "Unknown"

def parse_loot_line(text):
    return {coin: int(amount) for amount, coin in re.findall(r"(\d+)\s+(platinum|gold|silver|copper)", text.lower())}

def initialize_stats_from_log(filepath):
    global total_kills, total_deaths
    total_kills = 0
    total_deaths = 0
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        pending_death = False
        for line in f:
            if "You have slain" in line:
                total_kills += 1
            if "You have been slain by" in line:
                pending_death = True
            elif pending_death and "You have lost experience." in line:
                total_deaths += 1
                pending_death = False

# === MONITOR ACTIVE LOG FILE ===
def monitor_active_log_file(callback):
    last_file = None
    while True:
        try:
            log_files = glob.glob(os.path.join(LOG_DIR, "eqlog_*.txt"))
            if not log_files:
                print("[ERROR] No log files found.")
                time.sleep(1)
                continue
            current_file = max(log_files, key=os.path.getmtime)
            if current_file != last_file:
                print(f"[INFO] Switching to new log file: {current_file}")
                callback(current_file)
                last_file = current_file
        except Exception as e:
            print(f"[ERROR] Log monitor failed: {e}")
        time.sleep(2)

def on_new_log_file(filepath):
    initialize_stats_from_log(filepath)
    char_name = extract_character_name(filepath)
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        zone = extract_current_zone_from_lines(lines)
    print(f"[INFO] New log detected: {char_name} in {zone}")
    send_to_clients({
        "type": "status",
        "char_name": char_name,
        "current_zone": zone
    })
    send_stats_update()
    threading.Thread(target=monitor_log_file, args=(filepath,), daemon=True).start()

# === MONITOR LOG FILE ===
def monitor_log_file(filepath):
    global total_deaths, session_deaths, total_kills, session_kills

    print(f"[MONITOR] Monitoring log: {filepath}")
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        f.seek(0, os.SEEK_END)
        lines = []
        new_lines = []
        last_zone = None
        pending_death = False
        last_monster_slayed = None

        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue

            lines.append(line)
            new_lines.append(line)
            if len(lines) > 10000:
                lines.pop(0)
            if len(new_lines) > 1000:
                new_lines.pop(0)

            if "You have entered" in line:
                zone = extract_current_zone_from_lines(new_lines)
                if zone != last_zone:
                    char_name = extract_character_name(filepath)
                    print(f"[ZONE] {char_name} entered {zone}")
                    send_to_clients({
                        "type": "status",
                        "char_name": char_name,
                        "current_zone": zone
                    })
                    ##reset_session_stats()
                    send_stats_update()
                    last_zone = zone

            loot_event = False

            if "You receive" in line and "from the corpse" in line:
                coins = parse_loot_line(line)
                for coin_type, amount in coins.items():
                    print(f"[LOOT] {amount} {coin_type}")
                    send_to_clients({"type": "coin", "coin": coin_type, "count": amount})
                loot_event = True

            if "You receive" in line and "from" in line and "for the" in line:
                coins = parse_loot_line(line)
                for coin_type, amount in coins.items():
                    print(f"[SELL] {amount} {coin_type}")
                    send_to_clients({"type": "coin", "coin": coin_type, "count": amount})
                loot_event = True

            if "You have been slain by" in line:
                pending_death = True
                continue

            if pending_death and "You have lost experience." in line:
                total_deaths += 1
                session_deaths += 1
                print(f"[DEATH] Confirmed death")
                send_to_clients({"type": "death"})
                send_stats_update()
                pending_death = False
                continue

            if "You have slain" in line:
                total_kills += 1
                session_kills += 1
                print(f"[KILL] {line.strip()}")
                send_stats_update()
                continue

            if "has been slain by" in line:
                last_monster_slayed = time.time()
                continue

            if "You gain party experience" in line and last_monster_slayed:
                if time.time() - last_monster_slayed <= 2:
                    total_kills += 1
                    session_kills += 1
                    print(f"[KILL] Group kill credited to player")
                    send_stats_update()
                last_monster_slayed = None
                continue

            item_match = re.search(r"You have looted (?:a[n]?\s)?(.+?)\.", line)
            if item_match:
                item_name = item_match.group(1).strip("- ").strip()
                lookup_key = re.sub(r"[^a-z0-9 ]", "", item_name.lower()).strip()
                print(f"[LOOT] Item: {item_name} → Lookup: {lookup_key}")
                icon_id = item_icon_map.get(lookup_key)
                if icon_id:
                    icon_url = f"{ITEM_ICON_BASE_URL}/item_{icon_id}.png"
                    print(f"[LOOT] Icon: {icon_url}")
                    send_to_clients({"type": "item", "item": item_name, "icon": icon_url})
                    send_to_clients({"type": "item_toast", "item": item_name, "icon": icon_url})
                    loot_event = True
                else:
                    print(f"[WARN] No icon for: {item_name} (lookup: {lookup_key})")

            if loot_event:
                send_to_clients({"type": "bag_open"})

# === WEBSOCKET ===
async def ws_handler(websocket):
    connected_clients.add(websocket)
    try:
        log_file = find_latest_log_file()
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            char_name = extract_character_name(log_file)
            zone = extract_current_zone_from_lines(lines)
            await websocket.send(json.dumps({
                "type": "status",
                "char_name": char_name,
                "current_zone": zone
            }))
            await websocket.send(json.dumps({
                "type": "stats",
                "total_deaths": total_deaths,
                "session_deaths": session_deaths,
                "total_kills": total_kills,
                "session_kills": session_kills
            }))
        while True:
            await asyncio.sleep(1)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)

# === SERVERS ===
async def start_websocket_server():
    async with websockets.serve(ws_handler, "localhost", WS_PORT):
        print(f"[WS] WebSocket server running on ws://localhost:{WS_PORT}")
        await asyncio.Future()

def start_http_server():
    class Handler(SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                self.path = '/overlay.html'
            return super().do_GET()
    httpd = HTTPServer(("localhost", PORT), Handler)
    print(f"[HTTP] Serving overlay at http://localhost:{PORT}")
    httpd.serve_forever()

# === CLIENT MESSAGING ===
def send_to_clients(data):
    message = json.dumps(data)
    for client in list(connected_clients):
        asyncio.run_coroutine_threadsafe(client.send(message), main_loop)

# === FALLBACK LOG FINDER ===
def find_latest_log_file():
    log_files = glob.glob(os.path.join(LOG_DIR, "eqlog_*.txt"))
    if not log_files:
        raise FileNotFoundError("No EverQuest log files found in directory.")
    return max(log_files, key=os.path.getmtime)

# === MAIN ===
if __name__ == "__main__":
    try:
        load_item_icons()
        threading.Thread(target=monitor_active_log_file, args=(on_new_log_file,), daemon=True).start()
        threading.Thread(target=start_http_server, daemon=True).start()
        threading.Thread(target=lambda: main_loop.run_until_complete(start_websocket_server()), daemon=True).start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down.")
