from PyQt5.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from .config import AppMode, EcuConfig
from .sil_io_tab import PcSimIoTab
from .signalviewer_embed import EmbeddedSignalViewer


class EcuPage(QWidget):
    def __init__(self, ecu: EcuConfig, mode: AppMode, refresh_ms: int) -> None:
        super().__init__()
        self.ecu = ecu
        self.mode = mode

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"ECU: {ecu.name} | Mode: {mode.value} | CAN gate: {ecu.can_gate}"))

        tabs = QTabWidget()
        if mode == AppMode.SIL:
            tabs.addTab(PcSimIoTab(ecu, refresh_ms=refresh_ms), "I/O")

        tabs.addTab(EmbeddedSignalViewer(ecu, mode), "SignalViewer")
        layout.addWidget(tabs, 1)
