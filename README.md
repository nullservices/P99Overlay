# P99Overlay

🎥 A real-time stream overlay for **Project 1999 (EverQuest)** players that displays:
- Character info
- Zone name
- Total/session kills & deaths
- Looted coins and items with classic EverQuest-style animations

Perfect for Twitch streamers or personal stats tracking.

---

## 🔧 Features

- 📜 Real-time parsing of your P99 log file
- 💰 Animated coin collection when looting platinum/gold/silver/copper
- 🪙 Item icon popups with animated bag collection
- 🧍 Displays character name and zone
- 📊 Total and session stats for kills and deaths
- 🌐 HTML overlay for OBS or browser source

---

## 📦 Requirements

- Python 3.10+  
- Modern web browser (for the overlay)
- OBS or any streaming tool that supports browser sources

---

## 🚀 Getting Started

1. **Clone the repo**
   ```bash
   git clone https://github.com/nullservices/P99Overlay.git
   cd P99Overlay
   ```

2. **Install dependencies**
   ```python
   pip install websockets
   ```

4. **Configure your `config.json`**
   Create a file named `config.json` in the root folder:

   ```json
   {
     "log_dir": "H:/P99/Logs",
     "port": 8000,
     "ws_port": 6789
   }
   ```

   Update `log_dir` to your EverQuest log file directory.

5. **Run the overlay**
   ```bash
   python src/overlay.py
   ```

   You should see logs like:
   ```
   [MONITOR] Watching H:/P99/Logs\eqlog_PlayerName_P1999Green.txt
   [HTTP] Serving overlays at http://localhost:8000
   Available overlays:
     ▶ Loot     → http://localhost:8000/overlay_loot.html
     ▶ Spells   → http://localhost:8000/overlay_spells.html
     ▶ Buffs    → http://localhost:8000/overlay_buffs.html
     ▶ Header   → http://localhost:8000/overlay_header.html
   [WS] WebSocket server running on ws://localhost:6789
   ```

6. **Add it to OBS**

   - Add a new **Browser Source**
   - Set the URL to the available below
        ▶ Loot     → http://localhost:8000/overlay_loot.html
        ▶ Spells   → http://localhost:8000/overlay_spells.html
        ▶ Buffs    → http://localhost:8000/overlay_buffs.html
        ▶ Header   → http://localhost:8000/overlay_header.html
   - Set the dimensions to match your stream (e.g., 1920x1080)

---
