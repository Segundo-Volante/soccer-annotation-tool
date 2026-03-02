import sys
import logging
import traceback

# Configure logging BEFORE importing anything else
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler("/tmp/football_app.log", mode="w"),
    ],
)
logger = logging.getLogger(__name__)


def global_exception_hook(exc_type, exc_value, exc_tb):
    """Catch ALL unhandled Python exceptions and log them instead of letting
    PyQt6 call abort().  This is critical on macOS/Rosetta 2."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("Unhandled exception:\n%s", msg)
    print(f"\n{'='*60}\nUNHANDLED EXCEPTION:\n{msg}{'='*60}\n", file=sys.stderr, flush=True)


# Install BEFORE PyQt6 import so it catches everything
sys.excepthook = global_exception_hook


from PyQt6.QtWidgets import QApplication
from frontend.main_window import MainWindow


def main():
    logger.info("Starting Football Annotation Tool")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    logger.info("MainWindow shown, entering event loop")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
