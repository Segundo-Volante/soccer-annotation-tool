from PyQt6.QtCore import Qt, pyqtSignal, QObject


class ShortcutHandler(QObject):
    """Keyboard shortcut handler for V2 Tab+Number system.

    Number keys 1-9: Emitted as number_pressed(n).
        MainWindow decides: pending box → category, else → metadata option.
    Tab/Shift+Tab: cycle_dimension(forward).
    F/G/H: occlusion.  T: truncated.
    Enter/Esc/←/→: navigation.
    Ctrl+Z: undo.  Del: delete.  Ctrl+S: save.
    """

    # Number keys (1-9) — routed by MainWindow
    number_pressed = pyqtSignal(int)

    # Tab cycling for metadata dimensions
    cycle_dimension = pyqtSignal(bool)  # True = forward (Tab), False = backward (Shift+Tab)

    # Occlusion shortcuts
    occlusion_visible = pyqtSignal()     # F
    occlusion_partial = pyqtSignal()     # G
    occlusion_heavy = pyqtSignal()       # H
    truncated_toggle = pyqtSignal()      # T

    # Navigation
    export_advance = pyqtSignal()        # Enter
    skip_advance = pyqtSignal()          # Escape
    prev_frame = pyqtSignal()            # Left (when not zoomed)
    next_frame = pyqtSignal()            # Right (when not zoomed)
    pan_left = pyqtSignal()              # Left (when zoomed)
    pan_right = pyqtSignal()             # Right (when zoomed)
    pan_up = pyqtSignal()                # Up (when zoomed)
    pan_down = pyqtSignal()              # Down (when zoomed)

    # Edit
    undo = pyqtSignal()                  # Ctrl+Z
    delete_box = pyqtSignal()            # Delete
    force_save = pyqtSignal()            # Ctrl+S

    # AI-Assisted bulk operations
    bulk_assign = pyqtSignal(int)        # Ctrl+1 through Ctrl+6
    accept_all = pyqtSignal()            # Ctrl+A

    # Dashboard / Review / Export
    open_health = pyqtSignal()           # Ctrl+H
    open_review = pyqtSignal()           # Ctrl+R
    open_export_preview = pyqtSignal()   # Ctrl+E

    # Unsure
    mark_unsure = pyqtSignal()           # U

    # Box visibility
    cycle_box_visibility = pyqtSignal()  # B

    # Zoom
    zoom_in = pyqtSignal()               # Cmd/Ctrl + (or =)
    zoom_out = pyqtSignal()              # Cmd/Ctrl -
    reset_zoom = pyqtSignal()            # 0

    # Team color
    swap_teams = pyqtSignal()            # Ctrl+Shift+S

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_open = False
        self._is_zoomed_fn = None  # callable returning True if canvas is zoomed in

    def set_popup_open(self, is_open: bool):
        self._popup_open = is_open

    def handle_key(self, event) -> bool:
        if self._popup_open:
            return False

        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        # Ctrl combos
        if ctrl and key == Qt.Key.Key_Z:
            self.undo.emit()
            return True
        if ctrl and shift and key == Qt.Key.Key_S:
            self.swap_teams.emit()
            return True
        if ctrl and key == Qt.Key.Key_S:
            self.force_save.emit()
            return True

        # Ctrl+Number → bulk assign (AI-assisted mode)
        number_keys = {
            Qt.Key.Key_1: 1, Qt.Key.Key_2: 2, Qt.Key.Key_3: 3,
            Qt.Key.Key_4: 4, Qt.Key.Key_5: 5, Qt.Key.Key_6: 6,
            Qt.Key.Key_7: 7, Qt.Key.Key_8: 8, Qt.Key.Key_9: 9,
        }
        if ctrl and key in number_keys and 1 <= number_keys[key] <= 6:
            self.bulk_assign.emit(number_keys[key])
            return True

        # Ctrl+A → accept all pending as opponent
        if ctrl and key == Qt.Key.Key_A:
            self.accept_all.emit()
            return True

        # Ctrl+H → health dashboard
        if ctrl and key == Qt.Key.Key_H:
            self.open_health.emit()
            return True
        # Ctrl+R → review panel
        if ctrl and key == Qt.Key.Key_R:
            self.open_review.emit()
            return True
        # Ctrl+E → export preview
        if ctrl and key == Qt.Key.Key_E:
            self.open_export_preview.emit()
            return True

        # Ctrl+Plus / Ctrl+Equal → zoom in, Ctrl+Minus → zoom out
        if ctrl and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_in.emit()
            return True
        if ctrl and key == Qt.Key.Key_Minus:
            self.zoom_out.emit()
            return True

        # Tab / Shift+Tab → cycle metadata dimension
        if key == Qt.Key.Key_Tab:
            self.cycle_dimension.emit(not shift)  # Tab=forward, Shift+Tab=backward
            return True
        if key == Qt.Key.Key_Backtab:
            self.cycle_dimension.emit(False)
            return True

        # 0 key → reset zoom
        if not ctrl and key == Qt.Key.Key_0:
            self.reset_zoom.emit()
            return True

        # Number keys 1-9 (non-Ctrl)
        if not ctrl and key in number_keys:
            self.number_pressed.emit(number_keys[key])
            return True

        # Arrow keys: pan when zoomed, navigate when not
        zoomed = self._is_zoomed_fn() if self._is_zoomed_fn else False
        if key == Qt.Key.Key_Left:
            (self.pan_left if zoomed else self.prev_frame).emit()
            return True
        if key == Qt.Key.Key_Right:
            (self.pan_right if zoomed else self.next_frame).emit()
            return True
        if key == Qt.Key.Key_Up and zoomed:
            self.pan_up.emit()
            return True
        if key == Qt.Key.Key_Down and zoomed:
            self.pan_down.emit()
            return True

        # Simple key mapping
        mapping = {
            Qt.Key.Key_U: self.mark_unsure,
            Qt.Key.Key_B: self.cycle_box_visibility,
            Qt.Key.Key_F: self.occlusion_visible,
            Qt.Key.Key_G: self.occlusion_partial,
            Qt.Key.Key_H: self.occlusion_heavy,
            Qt.Key.Key_T: self.truncated_toggle,
            Qt.Key.Key_Return: self.export_advance,
            Qt.Key.Key_Enter: self.export_advance,
            Qt.Key.Key_Escape: self.skip_advance,
            Qt.Key.Key_Delete: self.delete_box,
            Qt.Key.Key_Backspace: self.delete_box,
        }

        signal = mapping.get(key)
        if signal:
            signal.emit()
            return True
        return False
