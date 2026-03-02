# Football Annotation Tool

A keyboard-driven PyQt6 desktop application for annotating soccer broadcast frames. Generates **RT-DETR training data** (COCO JSON + renamed frames) and **BoT-SORT Re-ID crops** (per-player cropped images) for player tracking. Works with **any team** and **any league** -- just load your own roster CSV and select the competition.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.5+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **Session dialog** -- Configure folder, roster CSV, competition, round, opponent, weather, and lighting per session
- **Tab + Number metadata system** -- 6 frame-level dimensions set via Tab cycling and number key selection
- **Bounding box annotation** -- Draw, move, resize boxes with category-colored outlines and pending box prompts
- **CSV roster system** -- Load any team's roster from a simple CSV file; Atletico de Madrid 2024-25 included as an example
- **Player roster auto-fill** -- Type a jersey number and the player name fills automatically from the loaded roster
- **Auto-skip** -- Frames tagged as replay, broadcast, crowd, overlay_heavy, or transition are skipped instantly
- **Metadata inheritance** -- Consecutive frames inherit the previous frame's metadata automatically
- **Real-time persistence** -- SQLite database with WAL mode saves every action; resume any session by reopening its folder
- **COCO JSON export** -- Per-frame annotations, combined dataset, cropped player images, and summary statistics
- **34 passing tests** covering models, database, file manager, and exporter

## Quick Start

### Prerequisites

- Python 3.10+
- pip

### Installation

```bash
git clone https://github.com/Segundo-Volante/soccer-annotation-tool.git
cd soccer-annotation-tool
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

### Run Tests

```bash
python -m pytest tests/ -v
```

---

## How It Works

### Step 1 -- Annotate Frames

The main workspace shows the current frame with a **filmstrip** on the left for navigation, the **annotation panel** on the right, and the **metadata bar** at the bottom. Click and drag anywhere on the frame to draw a bounding box around a player, referee, or the ball. An amber dashed box appears -- press a number key **1-6** to assign it a category.

![Annotation View](screenshots/annotation_view.png)

Each bounding box is **color-coded by category**: red for home players, blue for opponents, orange for home GK, dark blue for opponent GK, yellow for referees, and green for the ball. For home team players (keys 1 and 3), a popup asks for the jersey number -- the player name auto-fills from the loaded roster CSV.

The **right panel** lists every box on the current frame with the player's jersey number, name, and occlusion status. Click any entry to select it on the canvas. Double-click to edit player info. Use `Delete` to remove a box or `Ctrl+Z` to undo.

![Annotation Panel](screenshots/annotation_panel.png)

### Step 2 -- Set Frame Metadata (Tab + Number System)

Each frame has **6 metadata dimensions**. Press **Tab** to cycle to the next dimension (or **Shift+Tab** to go back). The active dimension is highlighted with an **amber border**. Then press a **number key (1-9)** to pick an option -- the selected value turns **bold amber**.

**SHOT** -- Describes the camera framing. Options in red (replay, broadcast, crowd) trigger auto-skip.

![Metadata - Shot Type](screenshots/metadata_shot.png)

**CAMERA** -- Describes camera movement. Transition triggers auto-skip.

![Metadata - Camera Motion](screenshots/metadata_camera.png)

**BALL** -- Ball visibility in the frame.

![Metadata - Ball Status](screenshots/metadata_ball.png)

**SITUATION** -- Current game state (open play, set piece, celebration, etc.).

![Metadata - Game Situation](screenshots/metadata_situation.png)

**ZONE** -- Which third of the pitch is shown.

![Metadata - Pitch Zone](screenshots/metadata_zone.png)

**QUALITY** -- Frame quality. Overlay_heavy and transition trigger auto-skip.

![Metadata - Frame Quality](screenshots/metadata_quality.png)

Metadata **carries over** automatically between consecutive frames -- only change what's different. Values shown in **red** trigger **auto-skip**, which instantly skips the frame and advances to the next one.

### Step 3 -- Export or Skip

Once all boxes are drawn and metadata is set, press **Enter** to export the frame (saves the renamed image, COCO JSON annotation, and cropped player images) or **Esc** to skip it. The tool then advances to the next unviewed frame.

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Cycle metadata dimension |
| `1-9` (no pending box) | Select metadata option |
| `1-6` (pending box) | Assign box category |
| `F` / `G` / `H` | Occlusion: visible / partial / heavy |
| `T` | Toggle truncated |
| `Enter` | Export frame + advance |
| `Esc` | Skip frame + advance |
| `Left` / `Right` | Previous / next frame |
| `Ctrl+Z` | Undo last box |
| `Delete` | Delete selected box |
| `Ctrl+S` | Force save |

## Categories

| Key | Category | Color |
|-----|----------|-------|
| 1 | Home Player | Red |
| 2 | Opponent | Blue |
| 3 | Home GK | Orange |
| 4 | Opponent GK | Dark Blue |
| 5 | Referee | Yellow |
| 6 | Ball | Green |

## Output Structure

```
your-folder/
├── annotations.db
└── output/
    ├── frames/            # Renamed images for RT-DETR
    ├── annotations/       # Per-frame COCO JSON
    ├── crops/             # Cropped player images for Re-ID
    │   ├── 07_Griezmann/
    │   ├── 19_Alvarez/
    │   ├── opponent/
    │   ├── referee/
    │   └── ball/
    ├── coco_dataset.json  # Combined COCO dataset
    └── summary.json       # Annotation statistics
```

### File Naming

```
{source}_{round}_{weather}_{lighting}_{shot}_{camera}_{situation}_{seq}.png
```

Example: `LaLiga_R15_clear_floodlight_wide_static_open-play_0001.png`

## Project Structure

```
soccer-annotation-tool/
├── main.py                 # Entry point
├── backend/
│   ├── models.py           # Data models (Category, BoundingBox, FrameAnnotation)
│   ├── database.py         # SQLite manager with WAL mode
│   ├── exporter.py         # COCO JSON + crop export
│   ├── file_manager.py     # Image I/O and folder scanning
│   └── roster_manager.py   # CSV roster loader + player lookup
├── frontend/
│   ├── main_window.py      # Main application window
│   ├── canvas.py           # Image display + box drawing
│   ├── metadata_bar.py     # Tab+Number metadata system
│   ├── annotation_panel.py # Box list + shortcuts reference
│   ├── filmstrip.py        # Thumbnail sidebar
│   ├── session_dialog.py   # Startup configuration dialog
│   ├── player_popup.py     # Jersey number input popup
│   ├── shortcuts.py        # Keyboard shortcut handler
│   ├── progress_bar.py     # Session progress display
│   └── toast.py            # Non-blocking overlay notifications
├── rosters/
│   └── atletico_madrid_2024-25.csv  # Example roster (CSV)
├── config/
│   ├── metadata_options.json  # 6 metadata dimensions + options
│   ├── categories.json        # Category definitions + colors
│   └── settings.json          # App settings
├── screenshots/            # App screenshots for documentation
├── tests/                  # 34 tests (pytest)
├── TUTORIAL.md             # Full usage guide
├── TUTORIAL.pdf            # PDF version of the tutorial
└── requirements.txt
```

## Configuration

### Roster (CSV)

The included `rosters/atletico_madrid_2024-25.csv` is just an **example**. You can create a CSV for **any team and any season** -- simply make a new file in the `rosters/` folder with 4 columns:

```csv
team,season,number,name
Manchester City,2024-25,9,Erling Haaland
Manchester City,2024-25,17,Kevin De Bruyne
Manchester City,2024-25,20,Bernardo Silva
```

When you launch the app, the session dialog lets you pick which roster CSV to load. The tool auto-fills player names when you type a jersey number during annotation, saving time on every bounding box.

### Supported Competitions

The source dropdown includes leagues and cups from 7 countries plus continental tournaments:

| Country | Leagues | Cups |
|---------|---------|------|
| Spain | LaLiga, LaLiga2 | Copa del Rey, Supercopa |
| England | EPL, EFL Championship | FA Cup, EFL Cup |
| France | Ligue 1, Ligue 2 | Coupe de France, Trophee des Champions |
| Italy | Serie A, Serie B | Coppa Italia, Supercoppa Italiana |
| Germany | Bundesliga, Bundesliga 2 | DFB-Pokal, DFL-Supercup |
| Portugal | Liga Portugal, Liga Portugal 2 | Taca de Portugal, Supertaca |
| Netherlands | Eredivisie, Eerste Divisie | KNVB Beker, Johan Cruyff Schaal |
| Continental | UCL, UEL, UECL | |

The source field is also **editable** -- you can type any competition name directly if it's not in the list.

To permanently add more leagues or cups, edit `frontend/session_dialog.py` and add entries to the `self._source_combo.addItems([...])` list.

### Metadata Options

Edit `config/metadata_options.json` to customize the 6 metadata dimensions, their options, defaults, and auto-skip rules.

## Documentation

See [TUTORIAL.md](TUTORIAL.md) for the full usage guide, or open [TUTORIAL.pdf](TUTORIAL.pdf) for a printable version.
