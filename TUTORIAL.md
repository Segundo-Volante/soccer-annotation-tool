# Soccer Annotation Tool — Quick Tutorial

## Getting Started

### 1. Launch the App
```bash
cd soccer-annotation-tool
python main.py
```

### 2. Session Setup Dialog
On launch, a startup dialog appears. Fill in:

1. **Folder** — Click "Browse..." to select the folder containing match screenshots (PNG, JPG, BMP, TIFF)
2. **Roster CSV** — Select a team roster CSV file (the default Atletico de Madrid 2024-25 is pre-selected). You can create your own CSV for any team — see the Roster section below.
3. **Source** — Competition: LaLiga, UCL, CopadelRey, Friendly, Supercopa
4. **Round** — e.g. `R15`, `QF`, `GS3`
5. **Opponent** — e.g. `Real Madrid`
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

> **Auto-skip:** Some values automatically skip the frame: `replay`, `broadcast`, `crowd` (SHOT), and `overlay_heavy`, `transition` (QUALITY). These are shown in red.

> **Metadata inheritance:** When advancing to a new frame, the previous frame's metadata is automatically carried forward. Only change what's different.

### Step 2 — Draw Bounding Boxes

Click and drag on the canvas to draw a rectangle around each player, referee, or ball.

- An amber dashed box appears with a category prompt: `1:ATL  2:OPP  3:GK  4:OGK  5:REF  6:BALL`
- Minimum box size is 5x5 pixels (prevents accidental micro-boxes)

### Step 3 — Assign a Category

After drawing a box, press a number key:

| Key | Category |
|-----|----------|
| **1** | Atletico Player → opens jersey number popup |
| **2** | Opponent |
| **3** | Atletico GK → opens jersey number popup |
| **4** | Opponent GK |
| **5** | Referee |
| **6** | Ball |

**For Atletico players (keys 1 and 3):** A popup appears asking for the jersey number. Type the number and the player name auto-fills from the roster. Press Enter to confirm or Escape to cancel.

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
- **Edit player info:** Double-click a box entry in the right panel (Atletico players only)

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
    │   ├── 07_Griezmann/
    │   ├── 19_Alvarez/
    │   ├── opponent/
    │   ├── opponent_gk/
    │   ├── referee/
    │   └── ball/
    ├── coco_dataset.json  <- combined COCO dataset (all frames)
    └── summary.json       <- annotation statistics
```

### File Naming (V2)

- **Frames:** `{source}_{round}_{weather}_{lighting}_{shot}_{camera}_{situation}_{seq}.png`
  - Example: `LaLiga_R15_clear_floodlight_wide_static_open-play_0001.png`
- **Crops:** `{source}_{round}_{seq}_{number}_{name}_{occlusion}.png`
  - Example: `LaLiga_R15_0001_07_Griezmann_visible.png`

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
      "category_name": "atletico_player",
      "occlusion": "visible",
      "truncated": false,
      "jersey_number": 7,
      "player_name": "Antoine Griezmann"
    }
  ]
}
```

---

## Tips

- **Speed:** The tool is designed for keyboard-driven annotation. Tab+Number metadata + draw box + number category = fast workflow.
- **Auto-skip:** Set SHOT to `replay`/`broadcast`/`crowd` or QUALITY to `overlay_heavy`/`transition` to instantly skip frames.
- **Metadata inheritance:** Consecutive similar frames inherit metadata from the previous frame — only change what's different.
- **Session resume:** Your work is saved in real-time to SQLite. Close the app any time — reopen the same folder to continue.
- **Overlapping boxes:** Allowed. Players do overlap in broadcast footage.
- **Duplicate jersey numbers:** Allowed with a warning (rare edge case).

---

## Roster (CSV)

Rosters are stored as CSV files in the `rosters/` folder. The default `atletico_madrid_2024-25.csv` is included.

To create a roster for any team or season, make a new CSV with 4 columns:

```csv
team,season,number,name
Real Madrid,2024-25,1,Thibaut Courtois
Real Madrid,2024-25,5,Jude Bellingham
Real Madrid,2024-25,7,Vinicius Jr
```

Place it in the `rosters/` folder and select it from the session dialog when you start annotating.

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
