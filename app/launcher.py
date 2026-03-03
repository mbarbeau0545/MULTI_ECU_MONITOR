import argparse
import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QMessageBox

from .config import ConfigValidationError
from .main_window import MultiEcuMonitorWindow


def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=r"Doc\ConfigPrj\ecus_config.json")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    try:
        win = MultiEcuMonitorWindow(Path(args.config).resolve())
    except ConfigValidationError as exc:
        QMessageBox.critical(None, "Configuration Error", str(exc))
        print(str(exc))
        sys.exit(2)
    except Exception as exc:
        QMessageBox.critical(None, "Startup Error", str(exc))
        print(str(exc))
        sys.exit(3)

    win.show()
    sys.exit(app.exec_())
