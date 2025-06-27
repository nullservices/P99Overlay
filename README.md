# 🎮 P99Overlay

A real-time stream overlay system for **Project 1999 (EverQuest)**. Built for Twitch streamers and immersive stat nerds.

---

## ✨ Features

- 📜 Live parsing of your EverQuest log file
- 🪙 Animated coin drops (Platinum, Gold, Silver, Copper)
- 📦 Item looting animation with classic EverQuest-style icons
- 📍 Character name & zone display
- ⚔️ Total and session-based kills and deaths
- ✨ Spell cast animations and fizzles
- 🧪 Buff bar with duration tracking
- 🌐 Modular HTML overlays for OBS/browser

---

## 🧰 Requirements

- Python 3.10+
- OBS Studio (or any browser source-friendly streaming app)
- Web browser (for local overlay testing)
- EQ log files enabled (`/log on` in-game)

---

## 🚀 Setup Instructions

### 1. Clone the Repo

```bash
git clone https://github.com/nullservices/P99Overlay.git
cd P99Overlay
```

### 2. Install Dependencies

```bash
pip install websockets
```

### 3. Update `config.json`

In the project config folder, update the log file location in the`config.json` file:

```json
{
  "log_dir": "H:/P99/Logs",
  "port": 8000,
  "ws_port": 6789
}
```

Update `log_dir` to your actual EverQuest log file directory.

### 4. Run the Overlay

```bash
python src/overlay.py
```

Example output:

```
[MONITOR] Watching H:/P99/Logs\eqlog_CharName_P1999Green.txt
[HTTP] Serving overlays at http://localhost:8000
[WS] WebSocket server running at ws://localhost:6789

Available Overlays:
 ▶ Loot     → http://localhost:8000/overlay_loot.html
 ▶ Spells   → http://localhost:8000/overlay_spells.html
 ▶ Buffs    → http://localhost:8000/overlay_buffs.html
 ▶ Header   → http://localhost:8000/overlay_header.html
```

### 5. Add to OBS

- Add a new **Browser Source** in OBS.
- Use one or more of the following URLs depending on the overlay type:

```
http://localhost:8000/overlay_loot.html
http://localhost:8000/overlay_spells.html
http://localhost:8000/overlay_buffs.html
http://localhost:8000/overlay_header.html
```

- Set the size (e.g., 1920×1080) and enable hardware acceleration for best performance.

---
