"""Export Preview dialog — shows what will be exported and in what format.

Lets the user choose between COCO JSON and YOLO TXT formats,
preview the output, and confirm export.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QGroupBox, QTextEdit,
    QFileDialog, QMessageBox, QFrame,
)

from backend.annotation_store import AnnotationStore
from backend.i18n import t
from backend.models import BoxStatus, CATEGORY_NAMES, FrameStatus

# ── Design tokens (unified with project palette) ──
_BG = "#1E1E2E"
_CARD = "#2A2A3C"
_ELEVATED = "#33334C"
_BORDER = "#404060"
_ACCENT = "#F5A623"
_ACCENT_HOVER = "#FFB833"
_TEXT = "#E8E8F0"
_MUTED = "#8888A0"
_BTN_BG = "#404060"
_BTN_HOVER = "#505070"

_DIALOG_STYLE = f"""
    QDialog {{ background: {_BG}; }}
    QLabel {{ color: {_TEXT}; font-size: 12px; }}
    QGroupBox {{
        color: {_MUTED}; font-size: 11px; border: 1px solid {_BORDER};
        border-radius: 6px; margin-top: 8px; padding-top: 16px;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
    QRadioButton {{ color: {_TEXT}; font-size: 12px; spacing: 6px; }}
    QRadioButton::indicator {{ width: 14px; height: 14px; }}
    QTextEdit {{
        background: {_CARD}; color: {_TEXT};
        border: 1px solid {_BORDER}; border-radius: 4px;
        font-family: monospace; font-size: 12px; padding: 8px;
    }}
    QPushButton {{
        background: {_BTN_BG}; color: {_TEXT}; padding: 8px 16px;
        border-radius: 4px; font-size: 12px; border: none;
    }}
    QPushButton:hover {{ background: {_BTN_HOVER}; }}
"""


class ExportPreviewDialog(QDialog):
    """Preview and configure dataset export."""

    def __init__(self, store: AnnotationStore, input_folder: str,
                 default_output: str, parent=None):
        super().__init__(parent)
        self._store = store
        self._input_folder = input_folder
        self._output_folder = default_output

        self.setWindowTitle(t("export.preview_title"))
        self.setMinimumSize(580, 500)
        self.resize(620, 540)
        self.setStyleSheet(_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── Title ──
        title = QLabel(t("export.preview_title"))
        title.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {_ACCENT};"
        )
        layout.addWidget(title)

        # Stats summary — compute complete vs needs_review breakdown
        stats = store.get_session_stats()
        complete_count = 0
        review_count = 0
        unsure_boxes_total = 0
        for frame in store.iter_all_frames():
            if frame.status != FrameStatus.ANNOTATED:
                continue
            has_unsure = any(b.box_status == BoxStatus.UNSURE for b in frame.boxes)
            if has_unsure:
                review_count += 1
                unsure_boxes_total += sum(
                    1 for b in frame.boxes if b.box_status == BoxStatus.UNSURE
                )
            else:
                complete_count += 1
        self._complete_count = complete_count
        self._review_count = review_count
        self._unsure_boxes_total = unsure_boxes_total

        summary_parts = [
            f"Complete: {complete_count}",
        ]
        if review_count > 0:
            summary_parts.append(
                f"Needs Review: {review_count} ({unsure_boxes_total} unsure boxes)"
            )
        summary_parts.append(f"Skipped: {stats['skipped']}")
        summary_parts.append(f"Total: {stats['total']}")
        summary = QLabel(" | ".join(summary_parts))
        summary.setStyleSheet(f"color: {_MUTED}; font-size: 12px;")
        layout.addWidget(summary)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_BORDER};")
        layout.addWidget(sep)

        # ── Format selection ──
        format_group = QGroupBox(t("export.format_label"))
        fmt_layout = QVBoxLayout(format_group)
        fmt_layout.setSpacing(8)

        self._format_group = QButtonGroup(self)
        self._coco_radio = QRadioButton(t("export.format_coco"))
        self._coco_radio.setChecked(True)
        self._yolo_radio = QRadioButton(t("export.format_yolo"))
        self._format_group.addButton(self._coco_radio, 0)
        self._format_group.addButton(self._yolo_radio, 1)
        fmt_layout.addWidget(self._coco_radio)
        fmt_layout.addWidget(self._yolo_radio)
        layout.addWidget(format_group)

        # ── Output folder ──
        out_layout = QHBoxLayout()
        out_label = QLabel(t("export.output_folder"))
        out_label.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: bold;")
        out_layout.addWidget(out_label)
        self._output_label = QLabel(self._output_folder)
        self._output_label.setStyleSheet(f"color: {_ACCENT}; font-size: 12px;")
        self._output_label.setWordWrap(True)
        out_layout.addWidget(self._output_label, stretch=1)
        browse_btn = QPushButton(t("button.browse"))
        browse_btn.clicked.connect(self._browse_output)
        out_layout.addWidget(browse_btn)
        layout.addLayout(out_layout)

        # ── Preview area ──
        preview_label = QLabel(t("export.preview_label"))
        preview_label.setStyleSheet(f"color: {_MUTED}; font-size: 11px; font-weight: bold;")
        layout.addWidget(preview_label)
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(160)
        layout.addWidget(self._preview)

        self._update_preview()
        self._format_group.buttonClicked.connect(lambda _: self._update_preview())

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(t("button.cancel"))
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {_MUTED};"
            f" padding: 10px 20px; border: 1px solid {_BORDER};"
            f" border-radius: 6px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {_CARD}; color: {_TEXT}; }}"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        export_btn = QPushButton(t("export.export_button"))
        export_btn.setStyleSheet(
            f"QPushButton {{ background: {_ACCENT}; color: {_BG}; padding: 10px 28px;"
            f" border-radius: 6px; font-weight: bold; font-size: 13px; border: none; }}"
            f"QPushButton:hover {{ background: {_ACCENT_HOVER}; }}"
        )
        export_btn.clicked.connect(self.accept)
        btn_layout.addWidget(export_btn)

        layout.addLayout(btn_layout)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, t("export.select_output"))
        if folder:
            self._output_folder = folder
            self._output_label.setText(folder)
            self._update_preview()

    def _update_preview(self):
        is_yolo = self._yolo_radio.isChecked()
        stats = self._store.get_session_stats()

        lines = []
        if is_yolo:
            lines.append("Format: YOLO TXT")
            lines.append(f"Output: {self._output_folder}/output_yolo/")
            lines.append("")
            lines.append("Structure:")
            lines.append("  images/train/   \u2014 image files")
            lines.append("  labels/train/   \u2014 YOLO .txt labels")
            lines.append("  data.yaml       \u2014 dataset config")
            lines.append("")
            lines.append(f"Frames to export: {stats['annotated']}")
            lines.append("")
            lines.append("Label format: class_id x_center y_center width height")
        else:
            lines.append("Format: COCO JSON")
            lines.append(f"Output: {self._output_folder}/output/")
            lines.append("")
            lines.append(f"Complete: {self._complete_count} frames \u2192 complete/")
            if self._review_count > 0:
                lines.append(
                    f"Needs Review: {self._review_count} frames "
                    f"({self._unsure_boxes_total} unsure boxes) \u2192 needs_review/"
                )
            lines.append(f"Skipped: {stats['skipped']}")
            lines.append("")
            lines.append("Structure:")
            lines.append("  complete/")
            lines.append("    frames/         \u2014 renamed images")
            lines.append("    annotations/    \u2014 per-frame COCO JSON")
            lines.append("    crops/          \u2014 cropped player images")
            lines.append("    coco_dataset.json")
            if self._review_count > 0:
                lines.append("  needs_review/")
                lines.append("    frames/         \u2014 frames with unsure boxes")
                lines.append("    annotations/    \u2014 per-frame COCO JSON")
                lines.append("    crops/          \u2014 cropped player images")
                lines.append("    coco_dataset.json")
                lines.append("    review_manifest.json \u2014 unsure box details")
            lines.append("  summary.json      \u2014 statistics")

        self._preview.setText("\n".join(lines))

    def get_result(self) -> dict:
        """Return export configuration."""
        return {
            "format": "yolo" if self._yolo_radio.isChecked() else "coco",
            "output_folder": self._output_folder,
        }
