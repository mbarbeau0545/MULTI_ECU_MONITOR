from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel, QMainWindow, QTabWidget, QVBoxLayout, QWidget

from .can_broker import PcSimCanBrokerService
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
        self._broker_stats_label = QLabel("CAN Broker: disabled")
        layout.addWidget(self._broker_stats_label)
        if self.cfg.warnings:
            warn_text = "Config warnings:\n" + "\n".join(f"- {w}" for w in self.cfg.warnings)
            warn_lbl = QLabel(warn_text)
            warn_lbl.setWordWrap(True)
            layout.addWidget(warn_lbl)

        tabs = QTabWidget()
        if not self.cfg.ecus:
            layout.addWidget(QLabel("No active ECU in config (set enable_ecu=true or ecu_in_debug=true)."))
        else:
            for ecu in self.cfg.ecus:
                tabs.addTab(EcuPage(ecu, self.cfg.mode, self.cfg.refresh_ms, self.cfg_path), ecu.name)
            layout.addWidget(tabs, 1)

        self._can_broker = PcSimCanBrokerService(self.cfg)
        self._broker_stats_timer = QTimer(self)
        self._broker_stats_timer.timeout.connect(self._update_broker_stats)
        self._broker_stats_timer.start(500)
        if self._can_broker.is_enabled:
            self._can_broker.start()
        self._update_broker_stats()

    def _update_broker_stats(self) -> None:
        if self._can_broker is None or not self._can_broker.is_enabled:
            self._broker_stats_label.setText("CAN Broker: disabled")
            return
        if self._can_broker.external_detected and not self._can_broker.is_owner:
            self._broker_stats_label.setText(
                f"CAN Broker: external detected on ctrl {self._can_broker.control_port}"
            )
            return
        st = self._can_broker.get_stats()
        self._broker_stats_label.setText(
            f"CAN Broker: running (ctrl {self._can_broker.control_port}) "
            f"rx={st.get('rx_frames', 0)} routed={st.get('routed_frames', 0)} "
            f"injected={st.get('injected_frames', 0)} dropped={st.get('dropped_frames', 0)} "
            f"cycle={st.get('last_cycle_ms', 0)}ms err={st.get('cycle_errors', 0)}"
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            if self._broker_stats_timer is not None:
                self._broker_stats_timer.stop()
            if self._can_broker is not None:
                self._can_broker.stop()
        except Exception:
            pass
        super().closeEvent(event)
