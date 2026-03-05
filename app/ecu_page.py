from pathlib import Path

from PyQt5.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from .config import AppMode, EcuConfig
from .detachable_tabs import DetachableTabManager
from .script_runner_tab import ScriptRunnerTab
from .sil_io_tab import PcSimIoTab
from .signalviewer_embed import EmbeddedSignalViewer


class EcuPage(QWidget):
    def __init__(self, ecu: EcuConfig, mode: AppMode, refresh_ms: int, cfg_path: Path) -> None:
        super().__init__()
        self.ecu = ecu
        self.mode = mode
        self.cfg_path = cfg_path

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"ECU: {ecu.name} | Mode: {mode.value} | CAN gate: {ecu.can_gate}"))

        tabs = QTabWidget()
        self._tabs_detacher = DetachableTabManager(tabs, self)
        if mode == AppMode.SIL:
            tabs.addTab(PcSimIoTab(ecu, refresh_ms=refresh_ms, cfg_path=cfg_path), "I/O")
            tabs.addTab(ScriptRunnerTab(ecu, cfg_path=cfg_path), "Scripts")

        tabs.addTab(EmbeddedSignalViewer(ecu, mode), "SignalViewer")
        layout.addWidget(tabs, 1)
