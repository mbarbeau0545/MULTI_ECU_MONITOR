from pathlib import Path

from PyQt5.QtWidgets import QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from .config import load_config
from .ecu_page import EcuPage


class MultiEcuMonitorWindow(QMainWindow):
    def __init__(self, cfg_path: Path) -> None:
        super().__init__()
        self.cfg_path = cfg_path
        self.cfg = load_config(cfg_path)

        self.setWindowTitle("Multi ECU Monitor")
        self.resize(1760, 1020)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        layout.addWidget(QLabel(f"Config: {cfg_path} | Global Mode: {self.cfg.mode.value}"))
        if self.cfg.warnings:
            warn_text = "Config warnings:\n" + "\n".join(f"- {w}" for w in self.cfg.warnings)
            warn_lbl = QLabel(warn_text)
            warn_lbl.setWordWrap(True)
            layout.addWidget(warn_lbl)

        tabs = QTabWidget()
        for ecu in self.cfg.ecus:
            tabs.addTab(EcuPage(ecu, self.cfg.mode, self.cfg.refresh_ms), ecu.name)
        layout.addWidget(tabs, 1)
