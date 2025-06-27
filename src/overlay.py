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

# === CONFIG ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "..", "config", "config.json")
ITEMS_CSV = os.path.join(BASE_DIR, "..", "data", "items_min.csv")
SPELLS_FILE = os.path.join(BASE_DIR, "..", "data", "spells_us.txt")
TEMPLATE_DIR = os.path.join(BASE_DIR, "..", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")
ITEM_ICON_BASE_URL = "https://raw.githubusercontent.com/nullservices/eqitemicons/refs/heads/main/itemicons"

if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError("Missing config.json file in config/")

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

LOG_DIR = config.get("log_dir", "H:/P99/Logs")
PORT = config.get("port", 8000)
WS_PORT = config.get("ws_port", 6789)

# === STATE ===
connected_clients = set()
main_loop = asyncio.new_event_loop()
asyncio.set_event_loop(main_loop)

item_icon_map = {}
spell_lookup = {}
effect_text_you = {}
fade_lines = {}

total_deaths = 0
session_deaths = 0
total_kills = 0
session_kills = 0

last_casted_spell = None
last_cast_time = 0

BUFF_TYPES = {1, 3, 4, 5, 7}

# === UTILITIES ===
def send_to_clients(data):
    message = json.dumps(data)
    for client in list(connected_clients):
        asyncio.run_coroutine_threadsafe(client.send(message), main_loop)

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

def strip_log_prefix(line):
    return re.sub(r"^\[\w+ \w+ \d+ \d+:\d+:\d+ \d+\] ", "", line).strip()

# === LOAD DATA ===
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

def load_spells():
    with open(SPELLS_FILE, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("^")
            if len(parts) > 144:
                spell = {
                    "id": int(parts[0]),
                    "name": parts[1],
                    "you": parts[6],
                    "other": parts[7],
                    "fades": parts[8],
                    "cast_time": int(parts[13]),
                    "duration_formula": int(parts[16]),
                    "duration": int(parts[17]),
                    "type": int(parts[83]),
                    "icon_id": int(parts[144])
                }
                spell_lookup[spell["name"].lower()] = spell
                if spell["you"]:
                    effect_text_you[spell["you"]] = spell
                if spell["fades"]:
                    fade_lines[spell["fades"]] = spell

def calculate_buff_duration(spell):
    return spell["duration"] * 6000 if spell["duration"] > 0 else 0

# === MAIN LOGIC ===
def find_latest_log_file():
    log_files = glob.glob(os.path.join(LOG_DIR, "eqlog_*.txt"))
    return max(log_files, key=os.path.getmtime) if log_files else None

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

def monitor_log_file(filepath):
    global total_deaths, session_deaths, total_kills, session_kills
    global last_casted_spell, last_cast_time

    print(f"[MONITOR] Watching {filepath}")
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, os.SEEK_END)
        lines = []
        last_zone = None
        last_monster_slayed = None
        pending_death = False

        while True:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue

            lines.append(line)
            if len(lines) > 1000:
                lines.pop(0)

            content = strip_log_prefix(line.strip())

            # ZONE
            if "You have entered" in content:
                zone = extract_current_zone_from_lines(lines)
                if zone != last_zone:
                    char_name = extract_character_name(filepath)
                    print(f"[ZONE] {char_name} entered {zone}")
                    send_to_clients({"type": "status", "char_name": char_name, "current_zone": zone})
                    send_stats_update()
                    last_zone = zone

            # COINS
            if "You receive" in content and ("from the corpse" in content or "from" in content):
                coins = parse_loot_line(content)
                for coin_type, amount in coins.items():
                    print(f"[COIN] {amount} {coin_type}")
                    send_to_clients({"type": "coin", "coin": coin_type, "count": amount})
                send_to_clients({"type": "bag_open"})

            # DEATH
            if "You have been slain by" in content:
                pending_death = True
            elif pending_death and "You have lost experience." in content:
                total_deaths += 1
                session_deaths += 1
                print("[DEATH] Confirmed death")
                send_to_clients({"type": "death"})
                send_stats_update()
                pending_death = False

            # KILLS
            if "You have slain" in content:
                total_kills += 1
                session_kills += 1
                print(f"[KILL] {content}")
                send_stats_update()
            elif "has been slain by" in content:
                last_monster_slayed = time.time()
            elif "You gain party experience" in content and last_monster_slayed and time.time() - last_monster_slayed < 2:
                total_kills += 1
                session_kills += 1
                print("[KILL] Group kill credited")
                send_stats_update()
                last_monster_slayed = None

            # ITEM LOOT
            item_match = re.search(r"You have looted (?:a[n]?\s)?(.+?)\.", content)
            if item_match:
                item_name = item_match.group(1).strip("- ").strip()
                lookup_key = re.sub(r"[^a-z0-9 ]", "", item_name.lower()).strip()
                icon_id = item_icon_map.get(lookup_key)
                if icon_id:
                    icon_url = f"{ITEM_ICON_BASE_URL}/item_{icon_id}.png"
                    send_to_clients({"type": "item", "item": item_name, "icon": icon_url})
                    send_to_clients({"type": "item_toast", "item": item_name, "icon": icon_url})
                    send_to_clients({"type": "bag_open"})
                else:
                    print(f"[WARN] No icon for {item_name}")

            # SPELL CASTING
            if "You begin casting" in content:
                match = re.search(r"You begin casting (.+?)\.", content)
                if match:
                    spell_name = match.group(1).strip()
                    spell = spell_lookup.get(spell_name.lower())
                    if spell:
                        icon_id = spell["icon_id"]
                        cast_time = spell["cast_time"]
                        last_casted_spell = (spell_name, icon_id)
                        last_cast_time = time.time()
                        send_to_clients({
                            "type": "casting",
                            "icon_id": icon_id,
                            "name": spell_name,
                            "cast_time": cast_time
                        })
            elif "Your spell is interrupted." in content:
                send_to_clients({"type": "interrupted"})
                last_casted_spell = None
                last_cast_time = 0
            elif "Your spell fizzles!" in content:
                if last_casted_spell:
                    spell_name, icon_id = last_casted_spell
                    send_to_clients({"type": "fizzle", "icon_id": icon_id, "name": spell_name})
                last_casted_spell = None
                last_cast_time = 0
            elif any(fade in content for fade in fade_lines):
                for fade_text, spell in fade_lines.items():
                    if fade_text in content:
                        send_to_clients({"type": "remove_buff", "name": spell["name"]})
                        break
            elif any(effect in content for effect in effect_text_you):
                if last_casted_spell and time.time() - last_cast_time < 3:
                    spell_name, icon_id = last_casted_spell
                    spell = spell_lookup.get(spell_name.lower())
                    if spell and spell["type"] in BUFF_TYPES:
                        duration = calculate_buff_duration(spell)
                        send_to_clients({
                            "type": "buff",
                            "icon_id": icon_id,
                            "name": spell_name,
                            "duration_ms": duration
                        })
                else:
                    for text, spell in effect_text_you.items():
                        if text in content and spell["type"] in BUFF_TYPES:
                            duration = calculate_buff_duration(spell)
                            send_to_clients({
                                "type": "buff",
                                "icon_id": spell["icon_id"],
                                "name": spell["name"],
                                "duration_ms": duration
                            })
                            break

# === WEBSOCKET + HTTP ===
async def ws_handler(websocket):
    connected_clients.add(websocket)
    try:
        log_file = find_latest_log_file()
        if log_file:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                char_name = extract_character_name(log_file)
                zone = extract_current_zone_from_lines(lines)
                await websocket.send(json.dumps({"type": "status", "char_name": char_name, "current_zone": zone}))
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

async def start_websocket_server():
    async with websockets.serve(ws_handler, "localhost", WS_PORT):
        print(f"[WS] WebSocket server running on ws://localhost:{WS_PORT}")
        await asyncio.Future()

def start_http_server():
    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            if path == "/":
                return os.path.join(TEMPLATE_DIR, "overlay_loot.html")
            elif path.endswith(".html"):
                return os.path.join(TEMPLATE_DIR, os.path.basename(path))
            elif path.startswith("/static/"):
                return os.path.join(STATIC_DIR, path[len("/static/"):])
            else:
                return super().translate_path(path)

    httpd = HTTPServer(("localhost", PORT), Handler)
    print(f"[HTTP] Serving overlays at http://localhost:{PORT}")
    print("Available overlays:")
    print(f"  ▶ Loot     → http://localhost:{PORT}/overlay_loot.html")
    print(f"  ▶ Spells   → http://localhost:{PORT}/overlay_spells.html")
    print(f"  ▶ Buffs    → http://localhost:{PORT}/overlay_buffs.html")
    print(f"  ▶ Header   → http://localhost:{PORT}/overlay_header.html")
    httpd.serve_forever()

# === MAIN ===
if __name__ == "__main__":
    try:
        load_item_icons()
        load_spells()
        log_file = find_latest_log_file()
        if not log_file:
            print("[ERROR] No log file found.")
            exit(1)

        initialize_stats_from_log(log_file)
        threading.Thread(target=monitor_log_file, args=(log_file,), daemon=True).start()
        threading.Thread(target=start_http_server, daemon=True).start()
        threading.Thread(target=lambda: main_loop.run_until_complete(start_websocket_server()), daemon=True).start()

        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("Shutting down.")