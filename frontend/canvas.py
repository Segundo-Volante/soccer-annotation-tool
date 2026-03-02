from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QImage, QColor, QPen, QFont, QBrush
from PyQt6.QtWidgets import QWidget

from backend.i18n import t
from backend.models import BoundingBox, Category, CATEGORY_NAMES, Occlusion

MIN_BOX_SIZE = 5
HANDLE_SIZE = 8


class CanvasMode(Enum):
    IDLE = auto()
    DRAWING = auto()
    MOVING = auto()
    RESIZING = auto()


class ResizeHandle(Enum):
    NONE = auto()
    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()


CATEGORY_COLORS = {
    Category.HOME_PLAYER: QColor("#E74C3C"),
    Category.OPPONENT: QColor("#3498DB"),
    Category.HOME_GK: QColor("#E67E22"),
    Category.OPPONENT_GK: QColor("#2980B9"),
    Category.REFEREE: QColor("#F1C40F"),
    Category.BALL: QColor("#2ECC71"),
}


class AnnotationCanvas(QWidget):
    box_drawn = pyqtSignal(int, int, int, int)  # x, y, w, h in image coords
    box_selected = pyqtSignal(int)  # box index
    box_deselected = pyqtSignal()
    box_moved = pyqtSignal(int, int, int, int, int)  # index, x, y, w, h
    box_resized = pyqtSignal(int, int, int, int, int)  # index, x, y, w, h

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._pixmap: Optional[QPixmap] = None
        self._boxes: list[BoundingBox] = []
        self._selected_index: int = -1

        # Pending box prompt (shown after drawing, before category assignment)
        self._pending_box_coords: Optional[tuple] = None

        # Display transform
        self._scale: float = 1.0
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0

        # Interaction state
        self._mode = CanvasMode.IDLE
        self._draw_start: Optional[QPoint] = None
        self._draw_current: Optional[QPoint] = None
        self._move_start: Optional[QPoint] = None
        self._move_box_origin: Optional[tuple] = None
        self._resize_handle = ResizeHandle.NONE
        self._resize_origin: Optional[tuple] = None

    def set_image(self, image_path: str):
        self._pixmap = QPixmap(image_path)
        self._boxes = []
        self._selected_index = -1
        self._pending_box_coords = None
        self._mode = CanvasMode.IDLE
        self._update_transform()
        self.update()

    def set_boxes(self, boxes: list[BoundingBox]):
        self._boxes = list(boxes)
        self._selected_index = -1
        self.update()

    def set_pending_box(self, x: int, y: int, w: int, h: int):
        """Show a pending box with category prompt overlay."""
        self._pending_box_coords = (x, y, w, h)
        self.update()

    def clear_pending_box(self):
        """Hide the pending box prompt."""
        self._pending_box_coords = None
        self.update()

    def get_selected_index(self) -> int:
        return self._selected_index

    def select_box(self, index: int):
        if 0 <= index < len(self._boxes):
            self._selected_index = index
            self.box_selected.emit(index)
        else:
            self._selected_index = -1
            self.box_deselected.emit()
        self.update()

    def clear_selection(self):
        self._selected_index = -1
        self.box_deselected.emit()
        self.update()

    # ── Coordinate conversion ──

    def _update_transform(self):
        if not self._pixmap:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        scale_x = cw / iw
        scale_y = ch / ih
        self._scale = min(scale_x, scale_y)
        self._offset_x = (cw - iw * self._scale) / 2
        self._offset_y = (ch - ih * self._scale) / 2

    def screen_to_image(self, sx: float, sy: float) -> tuple[int, int]:
        ix = (sx - self._offset_x) / self._scale
        iy = (sy - self._offset_y) / self._scale
        return int(ix), int(iy)

    def image_to_screen(self, ix: float, iy: float) -> tuple[int, int]:
        sx = ix * self._scale + self._offset_x
        sy = iy * self._scale + self._offset_y
        return int(sx), int(sy)

    def _image_rect_to_screen(self, x, y, w, h) -> QRect:
        sx, sy = self.image_to_screen(x, y)
        sw = int(w * self._scale)
        sh = int(h * self._scale)
        return QRect(sx, sy, sw, sh)

    # ── Hit testing ──

    def _hit_test_handle(self, pos: QPoint, box_idx: int) -> ResizeHandle:
        if box_idx < 0 or box_idx >= len(self._boxes):
            return ResizeHandle.NONE
        box = self._boxes[box_idx]
        rect = self._image_rect_to_screen(box.x, box.y, box.width, box.height)
        corners = {
            ResizeHandle.TOP_LEFT: rect.topLeft(),
            ResizeHandle.TOP_RIGHT: rect.topRight(),
            ResizeHandle.BOTTOM_LEFT: rect.bottomLeft(),
            ResizeHandle.BOTTOM_RIGHT: rect.bottomRight(),
        }
        for handle, corner in corners.items():
            if abs(pos.x() - corner.x()) <= HANDLE_SIZE and abs(pos.y() - corner.y()) <= HANDLE_SIZE:
                return handle
        return ResizeHandle.NONE

    def _hit_test_box(self, pos: QPoint) -> int:
        ix, iy = self.screen_to_image(pos.x(), pos.y())
        for i in range(len(self._boxes) - 1, -1, -1):
            b = self._boxes[i]
            if b.x <= ix <= b.x + b.width and b.y <= iy <= b.y + b.height:
                return i
        return -1

    # ── Mouse events ──

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._pixmap:
            return

        pos = event.pos()

        # Check resize handles on selected box
        if self._selected_index >= 0:
            handle = self._hit_test_handle(pos, self._selected_index)
            if handle != ResizeHandle.NONE:
                self._mode = CanvasMode.RESIZING
                self._resize_handle = handle
                box = self._boxes[self._selected_index]
                self._resize_origin = (box.x, box.y, box.width, box.height)
                self._move_start = pos
                return

        # Check box hit
        hit = self._hit_test_box(pos)
        if hit >= 0:
            self._selected_index = hit
            self.box_selected.emit(hit)
            self._mode = CanvasMode.MOVING
            self._move_start = pos
            box = self._boxes[hit]
            self._move_box_origin = (box.x, box.y)
            self.update()
            return

        # Start drawing new box
        self._selected_index = -1
        self.box_deselected.emit()
        self._mode = CanvasMode.DRAWING
        self._draw_start = pos
        self._draw_current = pos
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if self._mode == CanvasMode.DRAWING:
            self._draw_current = pos
            self.update()

        elif self._mode == CanvasMode.MOVING and self._move_start:
            dx = pos.x() - self._move_start.x()
            dy = pos.y() - self._move_start.y()
            dix = int(dx / self._scale)
            diy = int(dy / self._scale)
            box = self._boxes[self._selected_index]
            box.x = self._move_box_origin[0] + dix
            box.y = self._move_box_origin[1] + diy
            self.update()

        elif self._mode == CanvasMode.RESIZING and self._move_start and self._resize_origin:
            ox, oy, ow, oh = self._resize_origin
            dx = int((pos.x() - self._move_start.x()) / self._scale)
            dy = int((pos.y() - self._move_start.y()) / self._scale)
            box = self._boxes[self._selected_index]

            if self._resize_handle == ResizeHandle.TOP_LEFT:
                box.x = ox + dx
                box.y = oy + dy
                box.width = ow - dx
                box.height = oh - dy
            elif self._resize_handle == ResizeHandle.TOP_RIGHT:
                box.y = oy + dy
                box.width = ow + dx
                box.height = oh - dy
            elif self._resize_handle == ResizeHandle.BOTTOM_LEFT:
                box.x = ox + dx
                box.width = ow - dx
                box.height = oh + dy
            elif self._resize_handle == ResizeHandle.BOTTOM_RIGHT:
                box.width = ow + dx
                box.height = oh + dy

            box.width = max(MIN_BOX_SIZE, box.width)
            box.height = max(MIN_BOX_SIZE, box.height)
            self.update()

        else:
            # Update cursor
            if self._selected_index >= 0:
                handle = self._hit_test_handle(pos, self._selected_index)
                if handle != ResizeHandle.NONE:
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                    return
            hit = self._hit_test_box(pos)
            if hit >= 0:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._mode == CanvasMode.DRAWING and self._draw_start and self._draw_current:
            x1, y1 = self.screen_to_image(self._draw_start.x(), self._draw_start.y())
            x2, y2 = self.screen_to_image(self._draw_current.x(), self._draw_current.y())
            x = min(x1, x2)
            y = min(y1, y2)
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            if w >= MIN_BOX_SIZE and h >= MIN_BOX_SIZE:
                self.box_drawn.emit(x, y, w, h)

        elif self._mode == CanvasMode.MOVING and self._selected_index >= 0:
            box = self._boxes[self._selected_index]
            self.box_moved.emit(self._selected_index, box.x, box.y, box.width, box.height)

        elif self._mode == CanvasMode.RESIZING and self._selected_index >= 0:
            box = self._boxes[self._selected_index]
            self.box_resized.emit(self._selected_index, box.x, box.y, box.width, box.height)

        self._mode = CanvasMode.IDLE
        self._draw_start = None
        self._draw_current = None
        self._move_start = None
        self._resize_handle = ResizeHandle.NONE
        self.update()

    # ── Paint ──

    def resizeEvent(self, event):
        self._update_transform()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if not self._pixmap:
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             t("canvas.no_image"))
            painter.end()
            return

        # Draw image
        target = QRect(
            int(self._offset_x), int(self._offset_y),
            int(self._pixmap.width() * self._scale),
            int(self._pixmap.height() * self._scale),
        )
        painter.drawPixmap(target, self._pixmap)

        # Draw existing boxes (category-colored)
        for i, box in enumerate(self._boxes):
            is_selected = (i == self._selected_index)
            rect = self._image_rect_to_screen(box.x, box.y, box.width, box.height)

            color = CATEGORY_COLORS.get(box.category, QColor("#AAA"))
            if is_selected:
                pen = QPen(QColor(0, 255, 0), 3)
            else:
                pen = QPen(color, 2)
            painter.setPen(pen)
            painter.drawRect(rect)

            # Resize handles on selected box
            if is_selected:
                handle_color = QColor(0, 255, 0)
                for corner in [rect.topLeft(), rect.topRight(),
                               rect.bottomLeft(), rect.bottomRight()]:
                    painter.fillRect(
                        corner.x() - HANDLE_SIZE // 2,
                        corner.y() - HANDLE_SIZE // 2,
                        HANDLE_SIZE, HANDLE_SIZE,
                        handle_color,
                    )

        # Draw pending box with category prompt
        if self._pending_box_coords:
            px, py, pw, ph = self._pending_box_coords
            prect = self._image_rect_to_screen(px, py, pw, ph)

            # Amber dashed outline
            pen = QPen(QColor("#F5A623"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(prect)

            # Category prompt below box
            font = QFont("Arial", 10, QFont.Weight.Bold)
            painter.setFont(font)
            prompt = t("canvas.category_prompt")
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(prompt)
            th = fm.height()

            tx = prect.center().x() - tw // 2
            ty = prect.bottom() + 6

            # Clamp to widget bounds
            tx = max(4, min(tx, self.width() - tw - 12))
            ty = min(ty, self.height() - th - 8)

            # Background
            bg = QRect(tx - 6, ty - 2, tw + 12, th + 4)
            painter.fillRect(bg, QColor(30, 30, 46, 230))
            painter.setPen(QColor("#F5A623"))
            painter.drawText(tx, ty + th - fm.descent(), prompt)

        # Draw preview rectangle while drawing
        if self._mode == CanvasMode.DRAWING and self._draw_start and self._draw_current:
            pen = QPen(QColor(255, 0, 0), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            rect = QRect(self._draw_start, self._draw_current).normalized()
            painter.drawRect(rect)

        painter.end()

    def _build_label(self, box: BoundingBox) -> str:
        cat = box.category
        if cat in (Category.HOME_PLAYER, Category.HOME_GK):
            num = box.jersey_number or "?"
            name = box.player_name or ""
            parts = name.split()
            short = parts[-1] if parts else ""
            return f"#{num} {short}"
        return CATEGORY_NAMES.get(cat, "unknown")
