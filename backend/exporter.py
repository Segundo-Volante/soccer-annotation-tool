import json
import math
import shutil
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backend.annotation_store import AnnotationStore
from backend.file_manager import FileManager
from backend.models import (
    BoundingBox, BoxStatus, Category, CATEGORY_NAMES, FrameAnnotation,
    FrameStatus, METADATA_KEYS,
)


def _load_metadata_config(config_path: Optional[Path] = None) -> list[dict]:
    """Load frame-level metadata config with in_filename flags."""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "metadata_options.json"
    if not config_path.exists():
        return [
            {"key": "shot_type", "in_filename": True},
            {"key": "camera_motion", "in_filename": True},
            {"key": "ball_status", "in_filename": False},
            {"key": "game_situation", "in_filename": True},
            {"key": "pitch_zone", "in_filename": False},
            {"key": "frame_quality", "in_filename": False},
        ]
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data.get("frame_level", [])


def _ascii_normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return nfkd.encode("ASCII", "ignore").decode("ASCII")


def _extract_lastname(full_name: str) -> str:
    parts = full_name.strip().split()
    return _ascii_normalize(parts[-1]) if parts else "Unknown"


def _camera_angle_to_shot_type(camera_angle: str) -> str:
    """Derive shot_type from camera_angle."""
    if camera_angle in ("WIDE_CENTER", "WIDE_LEFT", "WIDE_RIGHT"):
        return "wide"
    if camera_angle == "MEDIUM":
        return "medium"
    if camera_angle == "CLOSEUP":
        return "closeup"
    return "other"


class Exporter:
    def __init__(self, store: AnnotationStore, input_folder: str | Path,
                 output_folder: str | Path, team_name: str = "Home Team",
                 has_opponent_roster: bool = False,
                 session_meta: Optional[dict] = None,
                 frame_metadata: dict[str, dict] | None = None,
                 bundle_metadata_raw: dict | None = None):
        self.store = store
        self.input_folder = Path(input_folder)
        self.output_folder = Path(output_folder)
        self._team_name = team_name
        self._has_opponent_roster = has_opponent_roster
        self._session_meta = session_meta or {}
        self._frame_metadata = frame_metadata or {}
        self._bundle_metadata_raw = bundle_metadata_raw or {}
        self._meta_config = _load_metadata_config()
        # Create two-folder output structure
        self._complete_dir = self.output_folder / "complete"
        self._review_dir = self.output_folder / "needs_review"
        FileManager.create_output_dirs(self._complete_dir)
        FileManager.create_output_dirs(self._review_dir)

    def validate_metadata(self, frame: FrameAnnotation) -> Optional[str]:
        """Return error message if metadata incomplete, else None."""
        for key in METADATA_KEYS:
            if not frame.metadata.get(key):
                return f"Set {key.replace('_', ' ')} before exporting"
        return None

    def _get_target_dir(self, frame: FrameAnnotation) -> Path:
        """Return complete/ or needs_review/ based on unsure boxes."""
        has_unsure = any(b.box_status == BoxStatus.UNSURE for b in frame.boxes)
        return self._review_dir if has_unsure else self._complete_dir

    def export_frame(self, frame: FrameAnnotation, filename: str) -> str:
        """Export a single frame.  Returns the exported filename."""
        seq = self.store.get_next_seq()
        exported_name = self._build_frame_name(frame, seq)
        target_dir = self._get_target_dir(frame)

        # 1. Copy original frame
        src = self.input_folder / frame.original_filename
        dst = target_dir / "frames" / exported_name
        shutil.copy2(str(src), str(dst))

        # 2. Generate per-frame COCO JSON
        json_name = Path(exported_name).stem + ".json"
        json_path = target_dir / "annotations" / json_name
        coco_data = self._build_coco_json(frame, exported_name)
        json_path.write_text(json.dumps(coco_data, indent=2, ensure_ascii=False), encoding="utf-8")

        # 3. Crop bounding boxes
        image = FileManager.load_image(src)
        if image is not None:
            crop_entries = self._export_crops(image, frame, seq, target_dir)
            self._update_crops_metadata(crop_entries, target_dir)

        # 4. Update combined dataset for the target folder
        self._update_combined_dataset(coco_data, target_dir)

        # 5. Update review manifest if frame has unsure boxes
        if any(b.box_status == BoxStatus.UNSURE for b in frame.boxes):
            self._update_review_manifest(frame, exported_name)

        # 6. Update summary
        self._update_summary()

        return exported_name

    def _build_frame_name(self, frame: FrameAnnotation, seq: int) -> str:
        parts = [
            frame.source or "Unknown",
            frame.match_round or "R00",
            frame.weather or "unknown",
            frame.lighting or "unknown",
        ]
        # Append frame-level metadata that has in_filename=true
        for dim in self._meta_config:
            if dim.get("in_filename", False):
                val = frame.metadata.get(dim["key"], "unknown")
                parts.append((val or "unknown").replace("_", "-"))
        parts.append(f"{seq:04d}")
        return "_".join(parts) + ".png"

    def _build_coco_json(self, frame: FrameAnnotation, exported_name: str) -> dict:
        annotations = []
        for i, box in enumerate(frame.boxes, 1):
            ann = {
                "id": i,
                "bbox": [box.x, box.y, box.width, box.height],
                "area": box.width * box.height,
                "category_id": box.category.value,
                "category_name": CATEGORY_NAMES[box.category],
                "occlusion": box.occlusion.value,
                "truncated": box.truncated,
                "box_status": box.box_status.value,
            }
            if box.jersey_number is not None:
                ann["jersey_number"] = box.jersey_number
            if box.player_name:
                ann["player_name"] = box.player_name
            ann["source"] = box.source.value
            if box.confidence is not None:
                ann["confidence"] = box.confidence
            if box.unsure_note:
                ann["unsure_note"] = box.unsure_note
            annotations.append(ann)

        # Build frame_metadata: session-level fields + all dynamic metadata
        frame_metadata = {
            "source": frame.source,
            "round": frame.match_round,
            "opponent": frame.opponent,
            "weather": frame.weather,
            "lighting": frame.lighting,
        }
        frame_metadata.update(frame.metadata)

        return {
            "image": {
                "file_name": exported_name,
                "width": frame.image_width,
                "height": frame.image_height,
            },
            "frame_metadata": frame_metadata,
            "annotations": annotations,
        }

    def _export_crops(self, image, frame: FrameAnnotation, seq: int,
                      target_dir: Path) -> list[dict]:
        source = frame.source or "Unknown"
        rnd = frame.match_round or "R00"
        opp_idx = 0
        ref_idx = 0
        crop_entries: list[dict] = []

        for box in frame.boxes:
            crop = FileManager.crop_region(image, box.x, box.y, box.width, box.height)
            if crop.size == 0:
                continue

            cat = box.category
            occ = box.occlusion.value

            if cat in (Category.HOME_PLAYER, Category.HOME_GK):
                num = box.jersey_number or 0
                lastname = _extract_lastname(box.player_name) if box.player_name else "Unknown"
                folder_name = f"home_{num:02d}_{lastname}"
                crop_name = f"{source}_{rnd}_{seq:04d}_{num:02d}_{lastname}_{occ}.png"
                crop_path = target_dir / "crops" / folder_name / crop_name

            elif cat in (Category.OPPONENT, Category.OPPONENT_GK):
                opp_idx += 1
                if self._has_opponent_roster and box.jersey_number is not None and box.player_name:
                    num = box.jersey_number
                    lastname = _extract_lastname(box.player_name)
                    folder_name = f"away_{num:02d}_{lastname}"
                    crop_name = f"{source}_{rnd}_{seq:04d}_{num:02d}_{lastname}_{occ}.png"
                else:
                    folder_name = "away"
                    crop_name = f"{source}_{rnd}_{seq:04d}_opp_{opp_idx:03d}_{occ}.png"
                crop_path = target_dir / "crops" / folder_name / crop_name

            elif cat == Category.REFEREE:
                ref_idx += 1
                crop_name = f"{source}_{rnd}_{seq:04d}_ref_{ref_idx:03d}_{occ}.png"
                crop_path = target_dir / "crops" / "referee" / crop_name

            elif cat == Category.BALL:
                crop_name = f"{source}_{rnd}_{seq:04d}_ball_{occ}.png"
                crop_path = target_dir / "crops" / "ball" / crop_name

            else:
                continue

            FileManager.save_image(crop, crop_path)

            # Build crop metadata entry
            crop_file = str(crop_path.relative_to(target_dir / "crops"))

            # Determine player_team from category
            if cat in (Category.HOME_PLAYER, Category.HOME_GK):
                player_team = "home"
            elif cat in (Category.OPPONENT, Category.OPPONENT_GK):
                player_team = "away"
            elif cat == Category.REFEREE:
                player_team = "referee"
            elif cat == Category.BALL:
                player_team = "ball"
            else:
                player_team = None

            # Look up frame metadata
            meta = self._frame_metadata.get(frame.original_filename, {})

            entry = {
                "crop_file": crop_file,
                "player_name": box.player_name or None,
                "player_team": player_team,
                "jersey_number": box.jersey_number,
                "category": CATEGORY_NAMES[box.category],
                "source_frame": frame.original_filename,
                "bbox": {"x": box.x, "y": box.y, "w": box.width, "h": box.height},
                "bbox_area_px": box.width * box.height,
                "occlusion": box.occlusion.value,
                "shot_type": _camera_angle_to_shot_type(meta.get("camera_angle", "")) if meta else None,
                "camera_angle": meta.get("camera_angle") if meta else None,
                "sequence_id": meta.get("sequence_id") if meta else None,
                "sequence_type": meta.get("sequence_type") if meta else None,
                "sequence_purpose": meta.get("sequence_purpose") if meta else None,
                "sequence_position": meta.get("sequence_position") if meta else None,
                "sequence_length": meta.get("sequence_length") if meta else None,
                "video_time": meta.get("video_time") if meta else None,
                "match_id": meta.get("match_id") if meta else None,
                "is_resample": meta.get("is_resample", False) if meta else False,
                "resample_of": meta.get("resample_of") if meta else None,
            }
            crop_entries.append(entry)

        return crop_entries

    def _update_crops_metadata(self, crop_entries: list[dict], target_dir: Path):
        """Append crop entries to crops_metadata.json, deduplicating by crop_file."""
        if not crop_entries:
            return
        meta_path = target_dir / "crops" / "crops_metadata.json"
        if meta_path.exists():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            data = {
                "export_info": {
                    "export_date": datetime.now(timezone.utc).isoformat(),
                    "match_id": self._session_meta.get("match_id", ""),
                    "competition": self._session_meta.get("source", ""),
                    "round": self._session_meta.get("match_round", ""),
                    "home_team": self._team_name,
                    "opponent": self._session_meta.get("opponent", ""),
                    "total_crops": 0,
                    "annotation_tool_version": "2.1.0",
                },
                "crops": [],
            }
        # Deduplicate: remove existing entries with same crop_file (re-export case)
        existing_files = {e["crop_file"] for e in crop_entries}
        data["crops"] = [c for c in data["crops"] if c.get("crop_file") not in existing_files]
        data["crops"].extend(crop_entries)
        data["export_info"]["total_crops"] = len(data["crops"])
        data["export_info"]["export_date"] = datetime.now(timezone.utc).isoformat()
        meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _update_combined_dataset(self, frame_coco: dict, target_dir: Path):
        dataset_path = target_dir / "coco_dataset.json"
        if dataset_path.exists():
            dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
        else:
            info = {"description": "Football annotation export"}
            if self._session_meta:
                for k in ("venue", "opponent", "weather", "lighting", "source", "match_round"):
                    if self._session_meta.get(k):
                        info[k] = self._session_meta[k]
            dataset = {
                "info": info,
                "images": [],
                "annotations": [],
                "categories": [
                    {"id": cat.value, "name": CATEGORY_NAMES[cat]}
                    for cat in Category
                ],
            }

        image_id = len(dataset["images"]) + 1
        image_entry = frame_coco["image"].copy()
        image_entry["id"] = image_id
        dataset["images"].append(image_entry)

        ann_offset = len(dataset["annotations"])
        for ann in frame_coco["annotations"]:
            entry = ann.copy()
            entry["id"] = ann_offset + entry["id"]
            entry["image_id"] = image_id
            entry["iscrowd"] = 0
            dataset["annotations"].append(entry)

        dataset_path.write_text(
            json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _update_review_manifest(self, frame: FrameAnnotation, exported_name: str):
        """Append unsure box info to review_manifest.json."""
        manifest_path = self._review_dir / "review_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {
                "frames_needing_review": [],
                "export_date": datetime.now(timezone.utc).isoformat(),
                "total_complete_frames": 0,
                "total_review_frames": 0,
            }

        unsure_boxes = []
        assigned_count = 0
        for box in frame.boxes:
            if box.box_status == BoxStatus.UNSURE:
                unsure_boxes.append({
                    "box_id": box.id,
                    "current_category": CATEGORY_NAMES.get(box.category, None),
                    "jersey_number": box.jersey_number,
                    "note": box.unsure_note or "",
                    "bbox": [box.x, box.y, box.width, box.height],
                })
            else:
                assigned_count += 1

        manifest["frames_needing_review"].append({
            "file_name": exported_name,
            "unsure_boxes": unsure_boxes,
            "assigned_boxes_count": assigned_count,
            "unsure_boxes_count": len(unsure_boxes),
        })
        manifest["total_review_frames"] = len(manifest["frames_needing_review"])
        manifest["export_date"] = datetime.now(timezone.utc).isoformat()

        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _update_summary(self):
        """Update the summary.json using data from the annotation store."""
        stats = self.store.get_session_stats()

        # Aggregate box counts and compute complete vs review breakdown
        by_category = {}
        by_player = {}
        total_boxes = 0
        complete_count = 0
        review_count = 0

        for frame in self.store.iter_all_frames():
            if frame.status != FrameStatus.ANNOTATED:
                continue
            has_unsure = any(b.box_status == BoxStatus.UNSURE for b in frame.boxes)
            if has_unsure:
                review_count += 1
            else:
                complete_count += 1
            for box in frame.boxes:
                cat_name = CATEGORY_NAMES.get(box.category, "unknown")
                by_category[cat_name] = by_category.get(cat_name, 0) + 1
                total_boxes += 1
                if box.jersey_number is not None and box.player_name:
                    key = f"{box.jersey_number:02d}_{_extract_lastname(box.player_name)}"
                    by_player[key] = by_player.get(key, 0) + 1

        # Get session metadata from any annotated frame
        source = ""
        match_round = ""
        opponent = ""
        for frame in self.store.iter_all_frames():
            if frame.source:
                source = frame.source
                match_round = frame.match_round or ""
                opponent = frame.opponent or ""
                break

        summary = {
            "session": {
                "source": source,
                "round": match_round,
                "opponent": opponent,
                "team": self._team_name,
            },
            "frames": {
                "total": stats["total"],
                "complete": complete_count,
                "needs_review": review_count,
                "skipped": stats["skipped"],
                "remaining": stats["unviewed"] + stats["in_progress"],
            },
            "annotations": {
                "total_boxes": total_boxes,
                "by_category": by_category,
                "by_player": by_player,
            },
        }

        summary_path = self.output_folder / "summary.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # ── Crop Distribution Analysis ──

    def compute_crop_distribution(
        self, targets: dict[str, int],
    ) -> dict:
        """Compute per-player per-shot-type crop counts across all annotated frames.

        Returns the full crop_distribution structure ready for JSON serialization.
        """
        has_metadata = bool(self._frame_metadata)

        # player_key → {shot_type → count}
        player_crops: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # player_key → (name, jersey_number)
        player_info: dict[str, tuple[str, int | None]] = {}

        for frame in self.store.iter_all_frames():
            if frame.status != FrameStatus.ANNOTATED:
                continue
            for box in frame.boxes:
                # Only count home players with identity
                if box.category not in (Category.HOME_PLAYER, Category.HOME_GK):
                    continue
                if box.jersey_number is None or not box.player_name:
                    continue

                key = f"{box.jersey_number:02d}_{_extract_lastname(box.player_name)}"
                player_info[key] = (box.player_name, box.jersey_number)

                if has_metadata:
                    meta = self._frame_metadata.get(frame.original_filename, {})
                    shot_type = _camera_angle_to_shot_type(meta.get("camera_angle", ""))
                else:
                    shot_type = "unknown"

                player_crops[key][shot_type] += 1

        # Build player entries
        players = []
        for key in sorted(player_crops.keys()):
            name, number = player_info[key]
            by_type = dict(player_crops[key])
            total = sum(by_type.values())
            gaps = []
            if has_metadata:
                for shot_type, target_count in targets.items():
                    current = by_type.get(shot_type, 0)
                    if current < target_count:
                        gaps.append({
                            "shot_type": shot_type,
                            "current": current,
                            "target": target_count,
                            "deficit": target_count - current,
                        })

            players.append({
                "name": name,
                "jersey_number": number,
                "crops_by_shot_type": by_type,
                "total_crops": total,
                "gaps": gaps,
                "status": "gap" if gaps else "ok",
            })

        # Summary
        players_with_gaps = [p for p in players if p["status"] == "gap"]
        largest_gap_player = ""
        largest_gap_type = ""
        if players_with_gaps:
            max_deficit = 0
            for p in players_with_gaps:
                for g in p["gaps"]:
                    if g["deficit"] > max_deficit:
                        max_deficit = g["deficit"]
                        largest_gap_player = p["name"]
                        largest_gap_type = g["shot_type"]

        session_info = self._bundle_metadata_raw.get("session_info", {})
        match_id = session_info.get("match_id", self._session_meta.get("source", ""))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "match_id": match_id,
            "competition": self._session_meta.get("source", ""),
            "round": self._session_meta.get("match_round", ""),
            "team": self._team_name,
            "opponent": self._session_meta.get("opponent", ""),
            "targets": targets,
            "players": players,
            "summary": {
                "total_players": len(players),
                "players_ok": len(players) - len(players_with_gaps),
                "players_with_gaps": len(players_with_gaps),
                "largest_gap_player": largest_gap_player,
                "largest_gap_type": largest_gap_type,
            },
        }

    def generate_crop_distribution(self, targets: dict[str, int]) -> dict:
        """Compute and write crop_distribution.json. Returns the distribution data."""
        dist = self.compute_crop_distribution(targets)
        dist_path = self.output_folder / "crop_distribution.json"
        dist_path.write_text(
            json.dumps(dist, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return dist

    # ── Resample Request Generation ──

    def generate_resample_request(
        self,
        distribution: dict,
        targets: dict[str, int],
        thresholds: dict,
    ) -> str | None:
        """Generate resample_request_[match_id].json for players with data gaps.

        Returns the output path, or None if no resample targets found.
        """
        session_info = self._bundle_metadata_raw.get("session_info", {})
        match_id = session_info.get("match_id", self._session_meta.get("source", ""))
        match_url = session_info.get("match_url", "")

        if not self._frame_metadata:
            return None

        # Collect sequence summary from raw metadata
        seq_summary = self._bundle_metadata_raw.get("sequence_summary", [])
        seq_by_id: dict[str, dict] = {s["sequence_id"]: s for s in seq_summary}

        # Build a map: (player_key, shot_type) → list of sequence_ids where visible
        # First gather per-frame: which players appear in which sequence
        # sequence_id → {player_key → count of frames}
        seq_player_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # sequence_id → {player_key → count of non-occluded frames}
        seq_player_visible: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for frame in self.store.iter_all_frames():
            if frame.status != FrameStatus.ANNOTATED:
                continue
            meta = self._frame_metadata.get(frame.original_filename, {})
            seq_id = meta.get("sequence_id")
            if not seq_id:
                continue
            for box in frame.boxes:
                if box.category not in (Category.HOME_PLAYER, Category.HOME_GK):
                    continue
                if box.jersey_number is None or not box.player_name:
                    continue
                key = f"{box.jersey_number:02d}_{_extract_lastname(box.player_name)}"
                seq_player_counts[seq_id][key] += 1
                if box.occlusion.value in ("visible", "partial"):
                    seq_player_visible[seq_id][key] += 1

        # For each player with gaps, find matching sequences
        estimated_interval = thresholds.get("estimated_resample_interval", 0.3)
        wide_ratio = thresholds.get("wide_min_player_ratio", 0.5)
        med_min = thresholds.get("medium_min_player_frames", 1)
        close_min = thresholds.get("closeup_min_player_frames", 1)
        min_seq_len = thresholds.get("min_sequence_length", 3)

        resample_targets = []

        for player in distribution.get("players", []):
            if player["status"] != "gap":
                continue

            gap_types = [g["shot_type"] for g in player["gaps"]]
            key = f"{player['jersey_number']:02d}_{_extract_lastname(player['name'])}"

            sequences = []
            for seq_id, seq_info in seq_by_id.items():
                seq_frame_count = seq_info.get("frame_count", 0)
                if seq_frame_count < min_seq_len:
                    continue

                seq_type = seq_info.get("sequence_type", "")
                # Map sequence_type to shot_type
                if "wide" in seq_type:
                    seq_shot = "wide"
                elif "medium" in seq_type:
                    seq_shot = "medium"
                elif "closeup" in seq_type or "close" in seq_type:
                    seq_shot = "closeup"
                else:
                    continue

                if seq_shot not in gap_types:
                    continue

                player_count = seq_player_counts.get(seq_id, {}).get(key, 0)
                player_vis = seq_player_visible.get(seq_id, {}).get(key, 0)

                # Apply thresholds
                if seq_shot == "wide":
                    ratio = player_count / seq_frame_count if seq_frame_count else 0
                    if ratio < wide_ratio:
                        continue
                elif seq_shot == "medium":
                    if player_vis < med_min:
                        continue
                elif seq_shot == "closeup":
                    if player_count < close_min:
                        continue

                # Gather visible players in this sequence
                visible_players = []
                for pk in seq_player_counts.get(seq_id, {}):
                    parts = pk.split("_", 1)
                    if len(parts) >= 2:
                        visible_players.append(parts[1])

                vt_start = seq_info.get("video_time_start", 0)
                vt_end = seq_info.get("video_time_end", 0)
                duration = vt_end - vt_start
                original_count = seq_frame_count
                expected_new = max(0, math.floor(duration / estimated_interval) - original_count)

                # Determine original interval from sequence_profiles_used
                profiles = session_info.get("sequence_profiles_used", {})
                orig_interval = None
                if seq_type in profiles:
                    orig_interval = profiles[seq_type].get("interval_sec")

                sequences.append({
                    "sequence_id": seq_id,
                    "sequence_type": seq_type,
                    "video_time_start": vt_start,
                    "video_time_end": vt_end,
                    "camera_angle": seq_info.get("camera_angle", "MEDIUM" if "medium" in seq_type else "CLOSEUP" if "close" in seq_type else "WIDE_CENTER"),
                    "original_interval_sec": orig_interval,
                    "original_frame_count": original_count,
                    "players_visible": visible_players,
                    "player_frame_count": player_count,
                    "player_frame_ratio": round(player_count / original_count, 2) if original_count else 0,
                    "expected_new_frames": expected_new,
                })

            if sequences:
                resample_targets.append({
                    "target_player": {
                        "name": player["name"],
                        "jersey_number": player["jersey_number"],
                        "gap_shot_types": gap_types,
                        "current_crops": player["crops_by_shot_type"],
                        "target_crops": targets,
                    },
                    "sequences": sequences,
                })

        if not resample_targets:
            return None

        # Summary stats
        total_seqs = sum(len(t["sequences"]) for t in resample_targets)
        total_new_frames = sum(
            s["expected_new_frames"] for t in resample_targets for s in t["sequences"]
        )
        total_video_time = sum(
            (s["video_time_end"] - s["video_time_start"])
            for t in resample_targets for s in t["sequences"]
        )
        est_minutes = (total_video_time + 10 * total_seqs) / 60

        request = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_bundle": match_id,
            "match_info": {
                "match_id": match_id,
                "competition": self._session_meta.get("source", ""),
                "round": self._session_meta.get("match_round", ""),
                "home_team": self._team_name,
                "opponent": self._session_meta.get("opponent", ""),
                "date": "",
                "match_url": match_url,
                "video_source": "footballia",
            },
            "generation_settings": {
                "targets": targets,
                "thresholds": {
                    "wide_min_player_ratio": wide_ratio,
                    "medium_min_player_frames": med_min,
                    "closeup_min_player_frames": close_min,
                    "min_sequence_length": min_seq_len,
                },
                "estimated_resample_interval": estimated_interval,
            },
            "resample_targets": resample_targets,
            "summary": {
                "total_players_with_gaps": len(resample_targets),
                "total_sequences_to_resample": total_seqs,
                "total_expected_new_frames": total_new_frames,
                "estimated_resample_time_minutes": round(est_minutes, 1),
            },
        }

        safe_id = match_id.replace(" ", "_").replace("/", "_")
        filename = f"resample_request_{safe_id}.json"
        out_path = self.output_folder / filename
        out_path.write_text(
            json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return str(out_path)
