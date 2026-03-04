# Football Annotation Tool

A keyboard-driven PyQt6 desktop application for annotating football broadcast frames. Generates **RT-DETR training data** (COCO JSON + YOLO TXT) and **BoT-SORT Re-ID crops** for player tracking. Works with **any team** and **any league**.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.5+-green)
![Tests](https://img.shields.io/badge/Tests-177_passing-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)

![Main Annotation View](screenshots/main_annotation_view.png)

> I just wanted to create something that lets more people who are truly passionate about football AI focus on what matters, without getting stuck in tedious technical details. You can annotate your data quickly and jump straight into building models.
>
> The tool was originally made to finish my Course Project, and now it's open-sourced in the hope that it can actually help others. Any suggestions, bug reports, or feature requests are super welcome! I'll update it as much as I can.

---

## Table of Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
  - [First-Run Setup](#step-0----first-run-setup)
  - [Annotate Frames](#step-1----annotate-frames)
  - [Frame Metadata](#step-2----set-frame-metadata-tab--number-system)
  - [Export or Skip](#step-3----export-or-skip)
- [AI-Assisted Mode](#ai-assisted-mode-optional)
- [Team Collaboration](#team-collaboration)
- [Tools](#tools)
  - [Health Dashboard](#health-dashboard-ctrlh)
  - [Review & Batch Edit](#review--batch-edit-ctrlr)
  - [Export Preview](#export-preview-ctrle)
- [Output Structure](#output-structure)
- [Architecture](#architecture)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Documentation](#documentation)

---

## Features

**Annotation**
- Draw, move, and resize bounding boxes with category-colored outlines
- 8-handle resize system (4 corners + 4 edge midpoints) for precise box adjustment
- Scroll wheel zoom centered on cursor, Cmd/Ctrl+=/- keyboard zoom, arrow key panning
- Three box visibility modes (Full / Subtle / Hidden) to reduce visual clutter
- Keyboard-first workflow -- every action mapped to a key (5-10s per frame)
- Player roster auto-fill from CSV (type jersey number, name fills automatically)
- Squad Sheet panel with click-to-assign: select a box, click a player row to assign instantly
- SquadList folder support: place player headshot images for quick visual identification
- Hover-to-enlarge player photos in the Squad Sheet for easy recognition
- Collapsible keyboard shortcuts bar in the stats area (toggle with "? Shortcuts" button)
- 6 configurable metadata dimensions per frame (shot, camera, ball, situation, zone, quality)
- Auto-skip for non-actionable frames (replays, broadcasts, crowd shots)

**AI-Assisted Mode**
- Optional YOLO/RT-DETR object detection auto-detects players, referees, and ball
- Reduces per-frame time from ~30-60s to ~5-10s
- Bulk assign categories with `Ctrl+1-6` or accept all with `Ctrl+A`
- Supports football-specific, COCO generic, and custom models

**Team Collaboration**
- Five workflow options: Solo, Split & Merge, Shared Folder, Git, and Custom
- Frame splitting with configurable ranges per annotator
- Merge with conflict resolution (keep first / latest / most boxes)
- Built-in Git interface with clone, connect, commit, push, and pull

**Quality & Review**
- Health Dashboard -- frame/box statistics, issue detection, category distribution
- Review & Batch Edit -- search, filter, and bulk-edit annotations across all frames
- Export Preview -- choose format and preview output structure before exporting
- Real-time stats bar with annotation speed, ETA, and session metrics

**Export & Persistence**
- COCO JSON export with per-frame annotations, combined dataset, and Re-ID crops
- YOLO TXT export with `data.yaml` for direct model training
- SQLite with WAL mode -- crash-safe, real-time auto-save, resume any session
- Dynamic metadata in exported filenames (competition, round, weather, etc.)

**Configuration**
- First-run setup wizard for team, season, roster, and competitions
- Multi-language support (English, Italian, German, Portuguese, French, Spanish)
- Config-driven categories, metadata dimensions, and competitions (JSON files)
- Opponent roster auto-detection from `config/teams/opponents/`

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/Segundo-Volante/football-annotation-tool.git
cd football-annotation-tool
pip install -r requirements.txt

# Optional: enable AI-assisted annotation mode
pip install -r requirements-ai.txt

# Run
python main.py

# Run tests
python -m pytest tests/ -v
```

On first launch, the **setup wizard** guides you through team configuration. After that, the **session dialog** opens for each annotation session.

---

## How It Works

### Step 0 -- First-Run Setup

On first launch (when `config/project.json` doesn't exist), a 3-step wizard appears:

1. **Team Setup** -- Enter team name, season, select language
2. **Competitions** -- Check which leagues and cups your team plays in
3. **Summary** -- Review and confirm

The wizard creates `config/project.json` with your team configuration and category definitions using `{home}` placeholders that resolve to your team name at runtime.

### Step 1 -- Annotate Frames

The main workspace shows the current frame with a **filmstrip** on the left for navigation, the **annotation panel** on the right, and the **metadata bar** at the bottom. Click and drag anywhere on the frame to draw a bounding box around a player, referee, or the ball. An amber dashed box appears -- press a number key **1-6** to assign it a category.

Each bounding box is **color-coded by category**:

| Key | Category | Color |
|-----|----------|-------|
| 1 | Home Player | Red |
| 2 | Opponent | Blue |
| 3 | Home GK | Orange |
| 4 | Opponent GK | Dark Blue |
| 5 | Referee | Yellow |
| 6 | Ball | Green |

For home team players (keys 1 and 3), a popup asks for the jersey number -- the player name auto-fills from the loaded roster CSV. For opponent players (keys 2 and 4), the popup appears only when an opponent roster CSV is available.

The **right panel** lists every box on the current frame with the player's jersey number, name, and occlusion status. Click any entry to select it on the canvas. Double-click to edit player info. Use `Delete` to remove a box or `Ctrl+Z` to undo.

![Annotation Panel](screenshots/annotation_panel.png)

### Step 2 -- Set Frame Metadata (Tab + Number System)

Each frame has **6 metadata dimensions** (configurable in `config/metadata_options.json`). Press **Tab** to cycle to the next dimension (or **Shift+Tab** to go back). The active dimension is highlighted with an **amber border**. Then press a **number key (1-9)** to pick an option -- the selected value turns **bold amber**.

Dimensions with `"in_filename": true` are included in exported filenames. Dimensions with `"in_filename": false` are stored in the COCO JSON only. Metadata **carries over** automatically between consecutive frames -- only change what's different. Values shown in **red** trigger **auto-skip**, which instantly skips the frame and advances to the next one.

<details>
<summary><b>View all 6 metadata dimensions</b></summary>

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

</details>

### Step 3 -- Export or Skip

Once all boxes are drawn and metadata is set, press **Enter** to export the frame or **Esc** to skip it.

---

## AI-Assisted Mode (Optional)

When `requirements-ai.txt` is installed, the session dialog offers an **AI-Assisted** annotation mode. Instead of drawing every bounding box manually, an object detection model auto-detects players, goalkeepers, referees, and the ball on each frame. You then review, resize, and assign identities -- reducing per-frame annotation time from ~30-60s to ~5-10s.

```bash
# Install AI dependencies (PyTorch, ultralytics, etc.)
pip install -r requirements-ai.txt
```

> See **[models.txt](models.txt)** for a detailed guide on available models, pre-downloading weights, and choosing the right model for your use case.

### Setup

1. Launch the app with `python main.py`
2. In the session dialog, select **AI-Assisted** for Annotation Mode
3. Choose a detection model from the dropdown (see model tiers below)
4. Set a confidence threshold (default 0.30 -- lower = more detections, higher = fewer but more accurate)
5. Click **Start Annotating** to begin the session

![AI Session Dialog](screenshots/ai_session_dialog.png)

### Available Models (3 tiers)

| Tier | Models | Classes | Download | Notes |
|------|--------|---------|----------|-------|
| **Football-specific** | RF-DETR (n/s/m), YOLO11 (n/s/m) | player, goalkeeper, referee, ball | From Roboflow (requires API key) | Best accuracy; auto-assigns referees and balls |
| **COCO generic** | YOLOv8 Nano / Small / Medium | person, sports ball | Auto-downloaded via ultralytics | No API key needed; all persons detected as pending |
| **Custom** | Any `.pt` file | Depends on model | User-provided | For custom-trained models |

**Football models** require a free [Roboflow API key](https://app.roboflow.com/settings/api). Set it as an environment variable before launching:

```bash
export ROBOFLOW_API_KEY="your_key_here"
python main.py
```

**COCO models** work out of the box -- no API key needed. Model weights are auto-downloaded on first use (~6-50 MB depending on size). See [models.txt](models.txt) for instructions on pre-downloading.

### Workflow

![AI Detection Example -- LaLiga](screenshots/ai_detection_example1.png)

![AI Detection Example -- Away Match](screenshots/ai_detection_example2.png)

1. **Navigate to a frame** -- AI detections appear automatically as **amber dashed boxes** labeled with class and confidence (e.g. "? person (0.92)"). A progress overlay shows the model name and elapsed time during detection.
2. **Review detections** -- Click any amber box to select it. **Drag corners** to resize, or **drag the center** to move it. Delete incorrect detections with `Delete`.
3. **Assign categories** -- Click a pending box and press **1-6** to assign it a category. For home players, the roster popup appears automatically for jersey number entry.
4. **Bulk assign** -- Use **Ctrl+1-6** to assign all pending boxes to a category at once. With football models, **Ctrl+2** (Opponent) skips goalkeeper-detected boxes.
5. **Accept all** -- Use **Ctrl+A** to accept all remaining pending boxes as Opponent (with confirmation dialog).
6. **Auto-assigned classes** -- Football models automatically assign referees (key 5) and balls (key 6). Only player/goalkeeper boxes need manual assignment.
7. **Export** -- Press **Enter** to export. Export is blocked while pending (unassigned) boxes remain.
8. **Re-detect** -- Click **Re-detect** in the AI status bar to clear pending boxes and re-run detection on the current frame.

### Performance Notes

- **First frame is slower** (~5-20s) because the model loads into memory. Subsequent frames are much faster (~0.5-3s).
- Detection runs in a **background thread** -- the UI stays responsive with a progress overlay.
- On Apple Silicon Macs running x86 Python (Rosetta 2), model loading may take longer. For best performance, use an ARM-native Python installation.
- **Nano** models are fastest, **Medium** models are most accurate. Start with Nano for large batches.

---

## Team Collaboration

The tool supports multi-person annotation projects with five collaboration workflows. Open **Settings > Collaboration** (or `Ctrl+Shift+C`) to configure.

![Collaboration Workflows](screenshots/collaboration_workflow_selection.png)

| Workflow | Description |
|----------|-------------|
| **Solo** | Single-person mode. No collaboration setup needed. |
| **Split & Merge** | Divide frames among team members, annotate independently, then merge results with conflict resolution. |
| **Shared Folder** | Use a cloud-synced folder (Google Drive, OneDrive, Dropbox) as the shared workspace. |
| **Git** | Version-controlled collaboration with branching, commits, and push/pull through a built-in Git interface. |
| **Custom** | Define your own workflow with custom instructions for your team. |

### Split & Merge

Divide frames across annotators by count or percentage. Each person works on their assigned range, then merge all annotations back together.

![Split Frames](screenshots/split_merge_divide_frames.png)

When merging, the tool detects conflicts (frames annotated by multiple people) and lets you choose how to resolve them -- keep first, keep latest, or keep the one with more boxes.

![Merge Annotations](screenshots/split_merge_annotations.png)

### Shared Folder

Connect a cloud-synced folder as your shared workspace. The setup guide walks through configuration for Google Drive, OneDrive, or Dropbox.

![Shared Folder Setup](screenshots/shared_folder_setup.png)

![Shared Folder Guide](screenshots/shared_folder_guide.png)

### Git Collaboration

Set up your identity, then clone a remote repository or connect an existing local repo. The built-in Git interface handles commits, pushes, and pulls.

![Git Setup](screenshots/git_collaboration_setup.png)

![Clone Repository](screenshots/git_clone_repo.png)

![Connect Repository](screenshots/git_connect_repo.png)

---

## Tools

Access built-in tools from the **Tools** menu to monitor annotation quality, review your work, and export datasets.

![Tools Menu](screenshots/tools_menu.png)

### Health Dashboard (`Ctrl+H`)

Real-time annotation quality analysis. The Overview tab shows frame and bounding box statistics. The Issues tab flags problems like missing boxes, duplicate frames, and jersey conflicts. The Distribution tab shows category and jersey number breakdowns.

![Health Dashboard -- Overview](screenshots/health_dashboard_overview.png)

![Health Dashboard -- Issues](screenshots/health_dashboard_issues.png)

![Health Dashboard -- Distribution](screenshots/health_dashboard_distribution.png)

### Review & Batch Edit (`Ctrl+R`)

Search and filter annotations across all frames. Jump to any frame directly from the results. Use batch edit to reassign jersey numbers across multiple frames at once.

![Review Panel](screenshots/review_panel.png)

### Export Preview (`Ctrl+E`)

Preview what will be exported before running the export. Choose between **COCO JSON** and **YOLO TXT** formats, set the output folder, and see the exact file structure that will be generated.

![Export Preview](screenshots/export_preview.png)

---

## Output Structure

### COCO JSON (default)

Exported frames are split into two folders based on annotation confidence:
- **`complete/`** — all boxes are finalized (ready for training)
- **`needs_review/`** — at least one box is marked unsure (needs expert review)

```
your-folder/
├── annotations.db
└── output/
    ├── complete/
    │   ├── frames/            # Renamed images (all boxes finalized)
    │   ├── annotations/       # Per-frame COCO JSON
    │   ├── crops/             # Cropped player images for Re-ID
    │   │   ├── home_07_Griezmann/
    │   │   ├── away/
    │   │   ├── referee/
    │   │   └── ball/
    │   └── coco_dataset.json  # Combined COCO dataset
    ├── needs_review/
    │   ├── frames/            # Frames with unsure boxes
    │   ├── annotations/       # Per-frame COCO JSON
    │   ├── crops/
    │   ├── coco_dataset.json
    │   └── review_manifest.json  # Unsure box details + notes
    └── summary.json           # Overall statistics
```

### YOLO TXT

```
your-folder/
└── output_yolo/
    ├── images/train/      # Image files
    ├── labels/train/      # YOLO .txt labels (class_id x_center y_center w h)
    └── data.yaml          # Dataset config for training
```

### File Naming

Only metadata dimensions with `"in_filename": true` appear in the filename:

```
{source}_{round}_{weather}_{lighting}_{shot}_{camera}_{situation}_{seq}.png
```

Example: `LaLiga_R15_clear_floodlight_wide_static_open-play_0001.png`

---

## Architecture

### Data Flow

```
User launches app
  │
  ├──▶ First run?  ──YES──▶  SetupWizard  ──▶  writes config/project.json
  │                                               │
  ▼                                               ▼
SessionDialog (folder, roster, opponent, weather, lighting, AI model)
  │
  ▼
Database creates session ──▶ FileManager scans folder ──▶ frames loaded
  │
  ▼
┌─────────────── ANNOTATION LOOP (per frame) ───────────────┐
│                                                           │
│  ┌─ Manual Mode ──────────────────────────────────────┐   │
│  │  Draw box on Canvas ──▶ press 1-6 ──▶ assign       │   │
│  │  category ──▶ PlayerPopup (jersey #) ──▶ save box  │   │
│  └────────────────────────────────────────────────────┘   │
│                                                           │
│  ┌─ AI-Assisted Mode ────────────────────────────────┐   │
│  │  Frame loads ──▶ YOLO runs in background thread    │   │
│  │  ──▶ amber PENDING boxes appear ──▶ user reviews   │   │
│  │  ──▶ resize / delete / press 1-6 to assign         │   │
│  │  ──▶ Ctrl+1-6 bulk assign ──▶ all boxes finalized  │   │
│  └────────────────────────────────────────────────────┘   │
│                                                           │
│  Set metadata (Tab to cycle, number to pick)              │
│  Enter = export frame  │  Esc = skip  │  ←/→ = navigate  │
│                                                           │
└───────────────────────────────────────────────────────────┘
  │
  ▼
Exporter reads DB ──▶ COCO JSON / YOLO TXT + renamed frames + Re-ID crops
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Keyboard-first** | Every action is mapped to a key. Mouse is only for drawing/resizing boxes. Keeps annotation speed at 5-10 seconds per frame. |
| **SQLite + WAL mode** | All annotations auto-save in real time. Crash-safe. Resume any session by reopening its folder. |
| **Metadata as JSON blob** | Flexible JSON column makes it easy to add new dimensions without schema migrations. |
| **AI is optional** | Core tool works without AI dependencies. Install `requirements-ai.txt` only if you want auto-detection. |
| **Background-thread detection** | YOLO inference runs on a separate QThread so the UI never freezes during detection. |
| **Config-driven** | Categories, metadata, competitions, and languages are all JSON config files. No code changes needed to customize. |

---

## Keyboard Shortcuts

### Annotation

| Key | Action |
|-----|--------|
| `1-6` (pending box) | Assign box category |
| `F` / `G` / `H` | Occlusion: visible / partial / heavy |
| `T` | Toggle truncated |
| `U` | Mark selected box as unsure (with optional note) |
| `Ctrl+Z` | Undo last box |
| `Delete` | Delete selected box |
| `Ctrl+S` | Force save |

### Metadata

| Key | Action |
|-----|--------|
| `Tab` / `Shift+Tab` | Cycle metadata dimension |
| `1-9` (no pending box) | Select metadata option |

### Navigation

| Key | Action |
|-----|--------|
| `Enter` | Export frame + advance |
| `Esc` | Skip frame + advance |
| `Left` / `Right` | Previous / next frame (navigate when not zoomed) |

### Zoom & View

| Key | Action |
|-----|--------|
| `Scroll wheel` / `Trackpad pinch` | Zoom in/out centered on cursor |
| `Cmd/Ctrl` + `=` | Zoom in (centered on mouse cursor) |
| `Cmd/Ctrl` + `-` | Zoom out (centered on mouse cursor) |
| `Arrow keys` (when zoomed) | Pan view |
| `Space` + drag / Middle-click drag | Pan view |
| `0` | Reset zoom to fit |
| `Double-click empty area` | Reset zoom |
| `B` | Cycle box visibility (Full / Subtle / Hidden) |

### AI Mode

| Key | Action |
|-----|--------|
| `1-6` (AI pending selected) | Assign category to AI box |
| `Ctrl+1-6` | Bulk assign all pending as category |
| `Ctrl+A` | Accept all pending as Opponent |

### Tools & Settings

| Key | Action |
|-----|--------|
| `Ctrl+H` | Open Health Dashboard |
| `Ctrl+R` | Open Review & Batch Edit |
| `Ctrl+E` | Open Export Preview |
| `Ctrl+Shift+C` | Open Collaboration Settings |

---

## Configuration

### Project Config (`config/project.json`)

Created by the setup wizard on first run. Contains:

```json
{
  "team_name": "FC Barcelona",
  "season": "2024-25",
  "language": "en",
  "competitions": ["LaLiga", "UCL", "CopadelRey"],
  "categories": [
    {"id": 0, "key": "home_player", "label": "{home} Player", "color": "#E53935", "roster": "home"},
    {"id": 1, "key": "opponent", "label": "Opponent", "color": "#1E88E5", "roster": "opponent_auto"}
  ]
}
```

The `{home}` placeholder in category labels is replaced with `team_name` at runtime.

### Roster (CSV)

Create a CSV with 4 columns for any team:

```csv
team,season,number,name
Manchester City,2024-25,9,Erling Haaland
Manchester City,2024-25,17,Kevin De Bruyne
```

**Home roster**: Set via `config/teams/home.json` or selected in the session dialog.

**Opponent rosters**: Drop CSV files in `config/teams/opponents/` named as `Team_Name.csv` (underscores become spaces in the UI). The session dialog shows a dropdown of available opponents.

### Metadata Options

Edit `config/metadata_options.json` to customize metadata dimensions. Each dimension has:
- `key`: Internal identifier
- `label`: Display name in the UI
- `options`: Available values
- `default`: Default value for new frames
- `auto_skip`: Values that trigger automatic frame skipping
- `in_filename`: Whether this dimension appears in exported filenames

### Multi-Language Support

Set `"language"` in `config/project.json` to one of: `en`, `it`, `de`, `pt`, `fr`, `es`. Add new languages by creating a JSON file in `config/i18n/` with the same keys as `en.json`.

---

## Project Structure

<details>
<summary><b>View full project tree</b></summary>

```
football-annotation-tool/
├── main.py                 # Entry point
├── backend/
│   ├── models.py           # Data models (Category, BoundingBox, FrameAnnotation)
│   ├── database.py         # SQLite manager with WAL mode + JSON metadata
│   ├── exporter.py         # COCO JSON + crop export with dynamic naming
│   ├── yolo_exporter.py    # YOLO TXT format export with data.yaml
│   ├── annotation_store.py # Annotation store for health/review tools
│   ├── file_manager.py     # Image I/O, folder scanning, reference crops
│   ├── squad_loader.py     # Squad JSON/SquadList loader + generator
│   ├── model_manager.py    # AI model manager (YOLO/RT-DETR, optional)
│   ├── roster_manager.py   # CSV roster loader + player lookup
│   ├── project_config.py   # Project configuration loader (project.json)
│   ├── session_stats.py    # Real-time session speed/ETA tracking
│   ├── collaboration.py    # Collaboration workflow manager
│   └── i18n.py             # JSON-based internationalization
├── frontend/
│   ├── main_window.py      # Main application window
│   ├── canvas.py           # Image display + box drawing
│   ├── metadata_bar.py     # Tab+Number metadata system
│   ├── annotation_panel.py # Box list panel
│   ├── squad_panel.py      # Squad Sheet with click-to-assign + hover enlarge
│   ├── filmstrip.py        # Thumbnail sidebar
│   ├── session_dialog.py   # Session configuration dialog
│   ├── setup_wizard.py     # First-run setup wizard
│   ├── player_popup.py     # Jersey number input popup
│   ├── shortcuts.py        # Keyboard shortcut handler
│   ├── progress_bar.py     # Session progress display
│   ├── stats_bar.py        # Real-time speed/ETA stats bar
│   ├── health_dashboard.py # Annotation health dashboard
│   ├── review_panel.py     # Review & batch edit panel
│   ├── export_preview_dialog.py # Export format preview dialog
│   ├── git_dialogs.py      # Git collaboration dialogs
│   ├── split_merge_dialogs.py   # Split & merge workflow dialogs
│   ├── shared_folder_dialogs.py # Shared folder workflow dialogs
│   └── toast.py            # Non-blocking overlay notifications
├── rosters/
│   └── atletico_madrid_2024-25.csv  # Example roster (CSV)
├── config/
│   ├── project.json            # Team config (team_name, categories, competitions)
│   ├── metadata_options.json   # Metadata dimensions + in_filename flags
│   ├── categories.json         # Category definitions + colors
│   ├── settings.json           # App settings
│   ├── teams/
│   │   ├── home.json           # Home team roster path
│   │   └── opponents/          # Opponent roster CSVs
│   └── i18n/
│       ├── en.json             # English
│       ├── it.json             # Italian
│       ├── de.json             # German
│       ├── pt.json             # Portuguese
│       ├── fr.json             # French
│       └── es.json             # Spanish
├── screenshots/            # App screenshots for documentation
├── tests/                  # 177 tests (pytest)
├── TUTORIAL.md             # Full usage guide
├── TUTORIAL.pdf            # PDF version of the tutorial
├── requirements.txt        # Base dependencies (PyQt6, OpenCV)
└── requirements-ai.txt     # Optional AI dependencies (ultralytics, torch)
```

</details>

---

## Documentation

See [TUTORIAL.md](TUTORIAL.md) for the full usage guide, or open [TUTORIAL.pdf](TUTORIAL.pdf) for a printable version.
