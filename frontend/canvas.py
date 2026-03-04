from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import QPainter, QPixmap, QImage, QColor, QPen, QFont, QBrush
from PyQt6.QtWidgets import QWidget

from backend.i18n import t
from backend.models import BoundingBox, BoxStatus, Category, CATEGORY_NAMES, Occlusion

MIN_BOX_SIZE = 5
HANDLE_SIZE = 8


class CanvasMode(Enum):
    IDLE = auto()
    DRAWING = auto()
    MOVING = auto()
    RESIZING = auto()


class BoxVisibilityMode(Enum):
    FULL = auto()     # All boxes, labels, confidence rendered normally
    SUBTLE = auto()   # 1px thin colored outlines at 40% opacity, no labels
    CLEAN = auto()    # No boxes or overlays rendered at all


class ResizeHandle(Enum):
    NONE = auto()
    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()
    LEFT = auto()
    RIGHT = auto()


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
    zoom_changed = pyqtSignal(int)  # zoom percentage (100 = fit-to-view)

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

        # Display transform (base fit-to-view)
        self._base_scale: float = 1.0
        self._scale: float = 1.0
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0

        # Zoom/pan state
        self._zoom_level: float = 1.0   # 1.0 = fit-to-view, max 5.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._space_held: bool = False
        self._panning: bool = False
        self._pan_last_pos: Optional[QPoint] = None

        # Box visibility mode (persists across frames)
        self._box_visibility = BoxVisibilityMode.FULL

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
        self._zoom_level = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._update_transform()
        self.zoom_changed.emit(100)
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

    @property
    def box_visibility(self) -> BoxVisibilityMode:
        return self._box_visibility

    def cycle_box_visibility(self):
        """Cycle: Full → Subtle → Clean → Full."""
        order = [BoxVisibilityMode.FULL, BoxVisibilityMode.SUBTLE, BoxVisibilityMode.CLEAN]
        idx = order.index(self._box_visibility)
        self._box_visibility = order[(idx + 1) % len(order)]
        self.update()

    # ── Coordinate conversion ──

    def _update_transform(self):
        if not self._pixmap:
            return
        iw, ih = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        self._base_scale = min(cw / iw, ch / ih)
        self._scale = self._base_scale * self._zoom_level
        self._offset_x = (cw - iw * self._scale) / 2 + self._pan_x
        self._offset_y = (ch - ih * self._scale) / 2 + self._pan_y

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

    # ── Zoom / Pan ──

    def _zoom_at(self, factor: float, cx: float, cy: float):
        """Zoom by factor centered on widget position (cx, cy)."""
        # Image point under cursor before zoom
        ix = (cx - self._offset_x) / self._scale
        iy = (cy - self._offset_y) / self._scale

        new_zoom = max(1.0, min(5.0, self._zoom_level * factor))
        # Use epsilon comparison to avoid floating-point drift blocking zoom
        if abs(new_zoom - self._zoom_level) < 1e-6:
            return
        self._zoom_level = new_zoom

        # Compute centered offset at new zoom (without pan)
        iw, ih = self._pixmap.width(), self._pixmap.height()
        cw, ch = self.width(), self.height()
        new_scale = self._base_scale * self._zoom_level
        center_ox = (cw - iw * new_scale) / 2
        center_oy = (ch - ih * new_scale) / 2

        # Set pan so cursor stays over same image point
        self._pan_x = cx - ix * new_scale - center_ox
        self._pan_y = cy - iy * new_scale - center_oy

        self._clamp_pan()
        self._update_transform()
        self.zoom_changed.emit(int(self._zoom_level * 100))
        self.update()

    def _clamp_pan(self):
        """Clamp pan so the image doesn't scroll beyond edges."""
        if not self._pixmap:
            return
        if self._zoom_level <= 1.0:
            self._pan_x = 0.0
            self._pan_y = 0.0
            return
        iw = self._pixmap.width()
        ih = self._pixmap.height()
        cw, ch = self.width(), self.height()
        img_w = iw * self._base_scale * self._zoom_level
        img_h = ih * self._base_scale * self._zoom_level
        max_pan_x = max(0, (img_w - cw) / 2)
        max_pan_y = max(0, (img_h - ch) / 2)
        self._pan_x = max(-max_pan_x, min(max_pan_x, self._pan_x))
        self._pan_y = max(-max_pan_y, min(max_pan_y, self._pan_y))

    def reset_zoom(self):
        """Reset zoom to fit-to-view."""
        self._zoom_level = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._update_transform()
        self.zoom_changed.emit(100)
        self.update()

    def set_space_held(self, held: bool):
        """Track Space key state for Space+drag panning."""
        self._space_held = held
        if held and self._zoom_level > 1.0:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif not held and not self._panning:
            self.setCursor(Qt.CursorShape.CrossCursor)

    @property
    def zoom_level(self) -> float:
        return self._zoom_level

    def zoom_in_step(self):
        """Zoom in by a fixed 15% step, centered on mouse cursor."""
        if not self._pixmap:
            return
        cursor_pos = self.mapFromGlobal(self.cursor().pos())
        if self.rect().contains(cursor_pos):
            cx, cy = cursor_pos.x(), cursor_pos.y()
        else:
            cx, cy = self.width() / 2, self.height() / 2
        self._zoom_at(1.15, cx, cy)

    def zoom_out_step(self):
        """Zoom out by a fixed 15% step, centered on mouse cursor."""
        if not self._pixmap:
            return
        cursor_pos = self.mapFromGlobal(self.cursor().pos())
        if self.rect().contains(cursor_pos):
            cx, cy = cursor_pos.x(), cursor_pos.y()
        else:
            cx, cy = self.width() / 2, self.height() / 2
        self._zoom_at(1 / 1.15, cx, cy)

    def pan_by(self, dx: float, dy: float):
        """Pan the view by (dx, dy) pixels. Only works when zoomed in."""
        if not self._pixmap or self._zoom_level <= 1.0:
            return
        self._pan_x += dx
        self._pan_y += dy
        self._clamp_pan()
        self._update_transform()
        self.update()

    def wheelEvent(self, event):
        # Always accept wheel events to prevent macOS from
        # rerouting them and stopping delivery to this widget
        event.accept()

        if not self._pixmap:
            return

        # macOS trackpad sends high-resolution pixelDelta
        if not event.pixelDelta().isNull():
            delta = event.pixelDelta().y()
            if abs(delta) < 1:
                return
            factor = 1 + delta * 0.002
        else:
            # Mouse wheel (both platforms)
            delta = event.angleDelta().y()
            if delta == 0:
                return
            factor = 1 + delta * 0.001

        # Clamp factor to avoid extreme jumps from trackpad momentum
        factor = max(0.8, min(1.25, factor))

        pos = event.position()
        self._zoom_at(factor, pos.x(), pos.y())

    # ── Hit testing ──

    def _hit_test_handle(self, pos: QPoint, box_idx: int) -> ResizeHandle:
        if box_idx < 0 or box_idx >= len(self._boxes):
            return ResizeHandle.NONE
        box = self._boxes[box_idx]
        rect = self._image_rect_to_screen(box.x, box.y, box.width, box.height)
        hs = HANDLE_SIZE + 2  # slightly larger hit area for easier grabbing

        # Check corners first (higher priority)
        corners = {
            ResizeHandle.TOP_LEFT: rect.topLeft(),
            ResizeHandle.TOP_RIGHT: rect.topRight(),
            ResizeHandle.BOTTOM_LEFT: rect.bottomLeft(),
            ResizeHandle.BOTTOM_RIGHT: rect.bottomRight(),
        }
        for handle, corner in corners.items():
            if abs(pos.x() - corner.x()) <= hs and abs(pos.y() - corner.y()) <= hs:
                return handle

        # Check edge midpoints
        edges = {
            ResizeHandle.TOP: QPoint(rect.center().x(), rect.top()),
            ResizeHandle.BOTTOM: QPoint(rect.center().x(), rect.bottom()),
            ResizeHandle.LEFT: QPoint(rect.left(), rect.center().y()),
            ResizeHandle.RIGHT: QPoint(rect.right(), rect.center().y()),
        }
        for handle, mid in edges.items():
            if abs(pos.x() - mid.x()) <= hs and abs(pos.y() - mid.y()) <= hs:
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
        if not self._pixmap:
            return

        pos = event.pos()

        # Middle-click pan
        if event.button() == Qt.MouseButton.MiddleButton:
            if self._zoom_level > 1.0:
                self._panning = True
                self._pan_last_pos = pos
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        # Space + left-click pan
        if self._space_held and self._zoom_level > 1.0:
            self._panning = True
            self._pan_last_pos = pos
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

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

        # Handle pan dragging
        if self._panning and self._pan_last_pos:
            dx = pos.x() - self._pan_last_pos.x()
            dy = pos.y() - self._pan_last_pos.y()
            self._pan_x += dx
            self._pan_y += dy
            self._pan_last_pos = pos
            self._clamp_pan()
            self._update_transform()
            self.update()
            return

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
            elif self._resize_handle == ResizeHandle.TOP:
                box.y = oy + dy
                box.height = oh - dy
            elif self._resize_handle == ResizeHandle.BOTTOM:
                box.height = oh + dy
            elif self._resize_handle == ResizeHandle.LEFT:
                box.x = ox + dx
                box.width = ow - dx
            elif self._resize_handle == ResizeHandle.RIGHT:
                box.width = ow + dx

            box.width = max(MIN_BOX_SIZE, box.width)
            box.height = max(MIN_BOX_SIZE, box.height)
            self.update()

        else:
            # Update cursor
            if self._space_held and self._zoom_level > 1.0:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                return
            if self._selected_index >= 0:
                handle = self._hit_test_handle(pos, self._selected_index)
                if handle in (ResizeHandle.TOP_LEFT, ResizeHandle.BOTTOM_RIGHT):
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                    return
                elif handle in (ResizeHandle.TOP_RIGHT, ResizeHandle.BOTTOM_LEFT):
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                    return
                elif handle in (ResizeHandle.TOP, ResizeHandle.BOTTOM):
                    self.setCursor(Qt.CursorShape.SizeVerCursor)
                    return
                elif handle in (ResizeHandle.LEFT, ResizeHandle.RIGHT):
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                    return
            hit = self._hit_test_box(pos)
            if hit >= 0:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseReleaseEvent(self, event):
        # End panning
        if self._panning and event.button() in (
            Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton
        ):
            self._panning = False
            self._pan_last_pos = None
            if self._space_held:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
            return

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

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._zoom_level > 1.0:
            hit = self._hit_test_box(event.pos())
            if hit < 0:
                self.reset_zoom()
                return
        super().mouseDoubleClickEvent(event)

    # ── Paint ──

    def resizeEvent(self, event):
        self._clamp_pan()
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

        # Draw existing boxes (category-colored or PENDING amber)
        label_font = QFont("Arial", 9, QFont.Weight.Bold)
        vis = self._box_visibility
        for i, box in enumerate(self._boxes):
            is_selected = (i == self._selected_index)
            rect = self._image_rect_to_screen(box.x, box.y, box.width, box.height)

            # Selected boxes always render at full visibility
            render_full = is_selected or vis == BoxVisibilityMode.FULL

            if vis == BoxVisibilityMode.CLEAN and not is_selected:
                continue  # Skip non-selected boxes entirely in Clean mode

            if box.box_status == BoxStatus.PENDING:
                if render_full:
                    # PENDING box: amber dashed border + semi-transparent fill
                    if is_selected:
                        pen = QPen(QColor(0, 255, 0), 3, Qt.PenStyle.DashLine)
                    else:
                        pen = QPen(QColor("#F5A623"), 2, Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(QColor(245, 166, 35, 25)))
                    painter.drawRect(rect)
                    painter.setBrush(Qt.BrushStyle.NoBrush)

                    # Label: "? player (0.92)" or "? person (0.85)"
                    painter.setFont(label_font)
                    cls_display = box.detected_class or "person"
                    conf_str = f" ({float(box.confidence):.2f})" if box.confidence else ""
                    label_text = f"? {cls_display}{conf_str}"
                    fm = painter.fontMetrics()
                    lx = rect.x() + 3
                    ly = rect.y() + 2
                    lw = fm.horizontalAdvance(label_text) + 6
                    lh = fm.height() + 4
                    painter.fillRect(lx - 2, ly, lw, lh, QColor(30, 30, 46, 200))
                    painter.setPen(QColor("#F5A623"))
                    painter.drawText(lx, ly + fm.height(), label_text)

                    # "AI" badge at top-right corner
                    ai_label = "AI"
                    ai_w = fm.horizontalAdvance(ai_label) + 8
                    ax = rect.right() - ai_w
                    ay = rect.y() + 2
                    painter.fillRect(ax, ay, ai_w, lh, QColor(245, 166, 35, 200))
                    painter.setPen(QColor("#1E1E2E"))
                    painter.drawText(ax + 4, ay + fm.height(), ai_label)
                else:
                    # Subtle mode: 1px thin amber outline at 40% opacity
                    subtle_color = QColor("#F5A623")
                    subtle_color.setAlpha(102)  # 40% of 255
                    painter.setPen(QPen(subtle_color, 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
            elif box.box_status == BoxStatus.UNSURE:
                unsure_color = QColor("#FF6B35")
                if render_full:
                    # UNSURE box: orange dashed border (category color if assigned)
                    if is_selected:
                        pen = QPen(QColor(0, 255, 0), 3, Qt.PenStyle.DashLine)
                    else:
                        cat_color = CATEGORY_COLORS.get(box.category, unsure_color)
                        pen = QPen(cat_color, 2, Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    painter.setBrush(QBrush(QColor(255, 107, 53, 25)))
                    painter.drawRect(rect)
                    painter.setBrush(Qt.BrushStyle.NoBrush)

                    # Label: "? unsure" or "? Home Player" or "? #7 Griezmann"
                    painter.setFont(label_font)
                    if box.jersey_number is not None and box.player_name:
                        parts = box.player_name.split()
                        short = parts[-1] if parts else ""
                        label_text = f"? #{box.jersey_number} {short}"
                    elif box.category is not None:
                        cat_name = CATEGORY_NAMES.get(box.category, "unknown")
                        label_text = f"? {cat_name}"
                    else:
                        label_text = "? unsure"
                    fm = painter.fontMetrics()
                    lx = rect.x() + 3
                    ly = rect.y() + 2
                    lw = fm.horizontalAdvance(label_text) + 6
                    lh = fm.height() + 4
                    painter.fillRect(lx - 2, ly, lw, lh, QColor(30, 30, 46, 200))
                    painter.setPen(unsure_color)
                    painter.drawText(lx, ly + fm.height(), label_text)
                else:
                    # Subtle mode: 1px thin orange outline at 40% opacity
                    subtle_color = QColor("#FF6B35")
                    subtle_color.setAlpha(102)
                    painter.setPen(QPen(subtle_color, 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
            elif box.box_status == BoxStatus.AUTO:
                color = CATEGORY_COLORS.get(box.category, QColor("#AAA"))
                if render_full:
                    # AUTO box: solid thin border in category color + "auto" badge
                    if is_selected:
                        pen = QPen(QColor(0, 255, 0), 3)
                    else:
                        pen = QPen(color, 1.5)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)

                    # Category label at top-left
                    painter.setFont(label_font)
                    cat_name = CATEGORY_NAMES.get(box.category, "")
                    fm = painter.fontMetrics()
                    lh = fm.height() + 4
                    if cat_name:
                        lx = rect.x() + 3
                        ly = rect.y() + 2
                        lw = fm.horizontalAdvance(cat_name) + 6
                        painter.fillRect(lx - 2, ly, lw, lh, QColor(30, 30, 46, 200))
                        painter.setPen(color)
                        painter.drawText(lx, ly + fm.height(), cat_name)

                    # "auto" badge at top-right
                    auto_label = "auto"
                    auto_w = fm.horizontalAdvance(auto_label) + 8
                    ax = rect.right() - auto_w
                    ay = rect.y() + 2
                    badge_bg = QColor(color)
                    badge_bg.setAlpha(180)
                    painter.fillRect(ax, ay, auto_w, lh, badge_bg)
                    painter.setPen(QColor("#1E1E2E"))
                    painter.drawText(ax + 4, ay + fm.height(), auto_label)
                else:
                    # Subtle mode: 1px thin category-colored outline at 40% opacity
                    subtle_color = QColor(color)
                    subtle_color.setAlpha(102)
                    painter.setPen(QPen(subtle_color, 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
            else:
                color = CATEGORY_COLORS.get(box.category, QColor("#AAA"))
                if render_full:
                    # FINALIZED box: category-colored solid border
                    if is_selected:
                        pen = QPen(QColor(0, 255, 0), 3)
                    else:
                        pen = QPen(color, 2)
                    painter.setPen(pen)
                    painter.drawRect(rect)
                else:
                    # Subtle mode: 1px thin category-colored outline at 40% opacity
                    subtle_color = QColor(color)
                    subtle_color.setAlpha(102)  # 40% of 255
                    painter.setPen(QPen(subtle_color, 1))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)

            # Resize handles on selected box (corners + edge midpoints)
            if is_selected:
                handle_color = QColor(0, 255, 0)
                edge_color = QColor(255, 255, 255)
                # Corner handles (green squares)
                for corner in [rect.topLeft(), rect.topRight(),
                               rect.bottomLeft(), rect.bottomRight()]:
                    painter.fillRect(
                        corner.x() - HANDLE_SIZE // 2,
                        corner.y() - HANDLE_SIZE // 2,
                        HANDLE_SIZE, HANDLE_SIZE,
                        handle_color,
                    )
                # Edge midpoint handles (white squares, slightly smaller)
                es = HANDLE_SIZE - 2
                for mid in [
                    QPoint(rect.center().x(), rect.top()),
                    QPoint(rect.center().x(), rect.bottom()),
                    QPoint(rect.left(), rect.center().y()),
                    QPoint(rect.right(), rect.center().y()),
                ]:
                    painter.fillRect(
                        mid.x() - es // 2, mid.y() - es // 2,
                        es, es, edge_color,
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

        # Mini zoom panel for selected box
        if 0 <= self._selected_index < len(self._boxes):
            self._draw_mini_zoom(painter)

        painter.end()

    def _draw_mini_zoom(self, painter: QPainter):
        """Draw a 200x200 mini zoom panel showing the selected box at 3x."""
        box = self._boxes[self._selected_index]
        if not self._pixmap:
            return

        panel_size = 200
        margin = 10

        # Determine magnification: 3x normally, 1.5x for large boxes
        box_screen_w = box.width * self._base_scale
        box_screen_h = box.height * self._base_scale
        if box_screen_w > self.width() * 0.5 or box_screen_h > self.height() * 0.5:
            mag = 1.5
        else:
            mag = 3.0

        # Source rect in image coords (centered on box)
        src_w = panel_size / mag
        src_h = panel_size / mag
        src_cx = box.x + box.width / 2
        src_cy = box.y + box.height / 2
        src_x = src_cx - src_w / 2
        src_y = src_cy - src_h / 2

        # Clamp to image bounds
        img_w = self._pixmap.width()
        img_h = self._pixmap.height()
        src_w = min(src_w, img_w)
        src_h = min(src_h, img_h)
        src_x = max(0, min(src_x, img_w - src_w))
        src_y = max(0, min(src_y, img_h - src_h))

        source_rect = QRect(int(src_x), int(src_y), int(src_w), int(src_h))

        # Target rect in bottom-right corner of widget
        tx = self.width() - panel_size - margin
        ty = self.height() - panel_size - margin
        target_rect = QRect(tx, ty, panel_size, panel_size)

        # Drop shadow
        painter.fillRect(tx + 3, ty + 3, panel_size, panel_size, QColor(0, 0, 0, 80))

        # Draw zoomed image region
        painter.drawPixmap(target_rect, self._pixmap, source_rect)

        # 1px dark border
        painter.setPen(QPen(QColor(60, 60, 80), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(target_rect)

        # Magnification label
        font = QFont("Arial", 9)
        painter.setFont(font)
        label = f"{mag:.1f}x"
        fm = painter.fontMetrics()
        lw = fm.horizontalAdvance(label) + 6
        lh = fm.height() + 2
        painter.fillRect(tx, ty, lw, lh, QColor(30, 30, 46, 200))
        painter.setPen(QColor(200, 200, 220))
        painter.drawText(tx + 3, ty + fm.height() - fm.descent(), label)

    def _build_label(self, box: BoundingBox) -> str:
        cat = box.category
        if cat in (Category.HOME_PLAYER, Category.HOME_GK):
            num = box.jersey_number or "?"
            name = box.player_name or ""
            parts = name.split()
            short = parts[-1] if parts else ""
            return f"#{num} {short}"
        return CATEGORY_NAMES.get(cat, "unknown")
