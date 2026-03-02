# Football Annotation Tool — Quick Tutorial

## Getting Started

### 1. Launch the App
```bash
cd football-annotation-tool
python main.py
```

### 2. First-Run Setup (one time only)

On the very first launch (when `config/project.json` doesn't exist), a **setup wizard** appears:

1. **Team Setup** — Enter your team name (e.g. "FC Barcelona"), season (e.g. "2024-25"), select a language (English, Italian, German, Portuguese, or French), and optionally browse for a home roster CSV
2. **Competitions** — Check all leagues and cups your team plays in (grouped by country)
3. **Summary** — Review your settings and click "Finish"

The wizard creates `config/project.json` and the `config/teams/` directory structure. You only do this once — after that, the session dialog opens directly.

### 3. Session Setup Dialog

Each time you launch the app, a session dialog appears. Fill in:

1. **Folder** — Click "Browse..." to select the folder containing match screenshots (PNG, JPG, BMP, TIFF)
2. **Roster CSV** — Select a team roster CSV file (or use the one configured in the wizard)
3. **Source** — Competition: populated from your setup wizard selections, or type your own
4. **Round** — e.g. `R15`, `QF`, `GS3`
5. **Opponent** — Select from the dropdown (auto-populated from `config/teams/opponents/`) or type a new name
6. **Weather** — Session default: Clear, Overcast, Rain, Snow, Fog
7. **Lighting** — Session default: Daylight Natural, Daylight Shadow, Floodlight, Mixed, Roof Closed

Click **"Start Annotating"** to begin.

> The app creates a local SQLite database (`annotations.db`) inside the folder. If you reopen the same folder later, it resumes where you left off.

---

## Annotation Workflow

For each frame, follow this order:

### Step 1 — Set Frame Metadata (Tab + Number system)

The **metadata bar** at the bottom shows 6 dimensions. Use **Tab** and **number keys** to set them:

| Key | Action |
|-----|--------|
| **Tab** | Cycle to next metadata dimension |
| **Shift+Tab** | Cycle to previous dimension |
| **1-9** | Select option for the active dimension |

#### The 6 Dimensions

| Dimension | Options |
|-----------|---------|
| **SHOT** | 1:wide 2:medium 3:tight 4:player_closeup 5:tactical 6:goal_line 7:replay 8:broadcast 9:crowd |
| **CAMERA** | 1:static 2:pan 3:zoom_in 4:zoom_out 5:tilt 6:tracking 7:crane 8:transition |
| **BALL** | 1:visible 2:partial 3:occluded 4:out_of_frame 5:in_air |
| **SITUATION** | 1:open_play 2:corner 3:free_kick 4:goal_kick 5:throw_in 6:penalty 7:kickoff 8:stopped 9:celebration |
| **ZONE** | 1:defensive_third 2:middle_third 3:attacking_third 4:full_pitch 5:penalty_area |
| **QUALITY** | 1:clean 2:motion_blur 3:overlay_heavy 4:transition |

> **In-filename flag:** Some dimensions appear in exported filenames (`in_filename: true` in `config/metadata_options.json`). By default, SHOT, CAMERA, and SITUATION are included in filenames; BALL, ZONE, and QUALITY are stored in COCO JSON only.

> **Auto-skip:** Some values automatically skip the frame: `replay`, `broadcast`, `crowd` (SHOT), and `overlay_heavy`, `transition` (QUALITY). These are shown in red.

> **Metadata inheritance:** When advancing to a new frame, the previous frame's metadata is automatically carried forward. Only change what's different.

### Step 2 — Draw Bounding Boxes

Click and drag on the canvas to draw a rectangle around each player, referee, or ball.

- An amber dashed box appears with a category prompt: `1:HOME  2:OPP  3:GK  4:OGK  5:REF  6:BALL`
- Minimum box size is 5x5 pixels (prevents accidental micro-boxes)

### Step 3 — Assign a Category

After drawing a box, press a number key:

| Key | Category |
|-----|----------|
| **1** | Home Player → opens jersey number popup |
| **2** | Opponent → opens jersey popup if opponent roster loaded |
| **3** | Home GK → opens jersey number popup |
| **4** | Opponent GK → opens jersey popup if opponent roster loaded |
| **5** | Referee |
| **6** | Ball |

**For home team players (keys 1 and 3):** A popup appears asking for the jersey number. Type the number and the player name auto-fills from the roster. Press Enter to confirm or Escape to cancel.

**For opponent players (keys 2 and 4):** The popup appears only when an opponent roster CSV is available in `config/teams/opponents/`. If no roster is loaded, the box is added without player info.

> **Key conflict resolution:** When a pending box is waiting for category (amber dashed box visible), keys 1-6 assign categories. When no box is pending, number keys select metadata options instead.

### Step 4 — Set Occlusion (optional)

After assigning a category, you can set how visible the player is:

| Key | Occlusion |
|-----|-----------|
| **F** | Fully visible |
| **G** | Partially occluded |
| **H** | Heavily occluded |
| **T** | Toggle truncated (player cut off at frame edge) |

> These apply to the most recently added box, or the currently selected box.

### Step 5 — Repeat

Draw more boxes for all remaining players, referees, and the ball in the frame.

### Step 6 — Export or Skip

| Key | Action |
|-----|--------|
| **Enter** | Export the frame and advance to the next |
| **Escape** | Skip the frame and advance to the next |

> **Note:** All 6 metadata dimensions must be set before exporting. The tool will warn you if any are missing.

---

## Editing Boxes

- **Select a box:** Click on it in the canvas, or click its entry in the right panel
- **Move a box:** Click and drag an existing box
- **Resize a box:** Select a box, then drag one of the green corner handles
- **Delete a box:** Select it and press **Delete** or **Backspace**, or click "Delete Selected"
- **Undo last box:** Press **Ctrl+Z**
- **Edit player info:** Double-click a box entry in the right panel

---

## Navigation

| Key | Action |
|-----|--------|
| **Left arrow** | Go to previous frame |
| **Right arrow** | Go to next frame |
| **Ctrl+S** | Force save current state |

You can also click any thumbnail in the filmstrip (left sidebar) to jump to that frame.

### Filmstrip Colors
- **Gray** — Unviewed
- **Yellow** — Currently selected / in progress
- **Blue** — Annotated and exported
- **Red** — Skipped

---

## Output

When you finish all frames, a completion dialog shows where your data was saved. All output goes to an `output/` folder inside your screenshot folder:

```
your-folder/
├── frame_001.png          <- your original screenshots
├── frame_002.png
├── ...
├── annotations.db         <- session database (auto-created)
└── output/
    ├── frames/            <- clean renamed images (for RT-DETR training)
    ├── annotations/       <- COCO JSON per frame (bounding box labels)
    ├── crops/             <- cropped player images (for Re-ID training)
    │   ├── home_07_Griezmann/     <- home players (named from roster)
    │   ├── home_19_Alvarez/
    │   ├── away_09_Haaland/       <- opponents (named, if roster loaded)
    │   ├── away/                  <- opponents (unnamed, no roster)
    │   ├── referee/
    │   └── ball/
    ├── coco_dataset.json  <- combined COCO dataset (all frames)
    └── summary.json       <- annotation statistics
```

### File Naming

Only metadata dimensions with `"in_filename": true` in `config/metadata_options.json` appear in the filename:

```
{source}_{round}_{weather}_{lighting}_{shot}_{camera}_{situation}_{seq}.png
```

Example: `LaLiga_R15_clear_floodlight_wide_static_open-play_0001.png`

### Crop Naming

- **Home players:** `home_{number}_{Lastname}/` (e.g. `home_07_Griezmann/`)
- **Opponents with roster:** `away_{number}_{Lastname}/` (e.g. `away_09_Haaland/`)
- **Opponents without roster:** `away/`
- **Referee:** `referee/`
- **Ball:** `ball/`

### COCO JSON Format

Each frame's annotation file contains:

```json
{
  "image": { "file_name": "...", "width": 1920, "height": 1080 },
  "frame_metadata": {
    "source": "LaLiga",
    "round": "R15",
    "opponent": "Real Madrid",
    "weather": "clear",
    "lighting": "floodlight",
    "shot_type": "wide",
    "camera_motion": "static",
    "ball_status": "visible",
    "game_situation": "open_play",
    "pitch_zone": "middle_third",
    "frame_quality": "clean"
  },
  "annotations": [
    {
      "id": 1,
      "bbox": [100, 200, 50, 80],
      "category_id": 0,
      "category_name": "home_player",
      "occlusion": "visible",
      "truncated": false,
      "jersey_number": 7,
      "player_name": "Antoine Griezmann"
    }
  ]
}
```

---

## Configuration

### Project Config (`config/project.json`)

Created by the setup wizard. Contains your team name, season, language, competitions, and category definitions. The `{home}` placeholder in category labels is replaced with your team name at runtime.

### Roster (CSV)

Create a CSV with 4 columns for any team:

```csv
team,season,number,name
Manchester City,2024-25,9,Erling Haaland
Manchester City,2024-25,17,Kevin De Bruyne
```

**Home roster:** Set during setup wizard or selected in the session dialog. Configured in `config/teams/home.json`.

**Opponent rosters:** Drop CSV files in `config/teams/opponents/` named as `Team_Name.csv` (underscores become spaces in the UI). The session dialog shows a dropdown of available opponents.

### Metadata Options (`config/metadata_options.json`)

Edit this file to customize metadata dimensions. Each frame-level dimension has:
- `key` — Internal identifier
- `label` — Display name in the UI
- `options` — Available values
- `default` — Default value for new frames
- `auto_skip` — Values that trigger automatic frame skipping
- `in_filename` — Whether this dimension appears in exported filenames

### Multi-Language Support

Set `"language"` in `config/project.json` to one of: `en`, `it`, `de`, `pt`, `fr`. Add new languages by creating a JSON file in `config/i18n/` with the same keys as `en.json`.

---

## Tips

- **Speed:** The tool is designed for keyboard-driven annotation. Tab+Number metadata + draw box + number category = fast workflow.
- **Auto-skip:** Set SHOT to `replay`/`broadcast`/`crowd` or QUALITY to `overlay_heavy`/`transition` to instantly skip frames.
- **Metadata inheritance:** Consecutive similar frames inherit metadata from the previous frame — only change what's different.
- **Session resume:** Your work is saved in real-time to SQLite. Close the app any time — reopen the same folder to continue.
- **Overlapping boxes:** Allowed. Players do overlap in broadcast footage.
- **Duplicate jersey numbers:** Allowed with a warning (rare edge case).
- **Any team:** Configure your team once in the setup wizard, then annotate any match.

---

## Keyboard Shortcut Quick Reference

| Key | Action |
|-----|--------|
| Tab / Shift+Tab | Cycle metadata dimension |
| 1-9 (no pending box) | Select metadata option |
| 1-6 (pending box) | Assign box category |
| F / G / H | Set occlusion: visible / partial / heavy |
| T | Toggle truncated |
| Enter | Export frame + advance |
| Escape | Skip frame + advance |
| Left / Right arrow | Previous / next frame |
| Ctrl+Z | Undo last box |
| Delete / Backspace | Delete selected box |
| Ctrl+S | Force save |
