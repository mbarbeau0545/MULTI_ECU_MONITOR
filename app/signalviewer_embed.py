import json
import sys
from pathlib import Path
from typing import Any, Dict

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from .config import AppMode, EcuConfig

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from IHM.IhmSigViewer import SignalViewer


class EmbeddedSignalViewer(QWidget):
    def __init__(self, ecu: EcuConfig, mode: AppMode) -> None:
        super().__init__()
        self.ecu = ecu
        self.mode = mode
        self.viewer = None

        layout = QVBoxLayout(self)
        try:
            prj_cfg = self._build_runtime_project_cfg()
            self.viewer = SignalViewer(str(prj_cfg))
            self.viewer.setParent(self)
            layout.addWidget(self.viewer)
        except Exception as exc:
            err = QLabel(f"SignalViewer init failed for {ecu.name}: {exc}")
            layout.addWidget(err)

    def _load_base_cfg(self) -> Dict[str, Any]:
        if self.ecu.project_software_cfg.suffix.lower() == ".json" and self.ecu.project_software_cfg.exists():
            try:
                return json.loads(self.ecu.project_software_cfg.read_text(encoding="utf-8"))
            except Exception:
                pass

        return {
            "signal_cfg": str(self.ecu.sym_file),
            "excel_cfg": str(self.ecu.project_software_cfg),
            "serial_cfg": {
                "baudrate": 115200,
                "port_com": "",
                "frame_len": 0,
                "is_enable": False,
                "enable_srl_msg_logg": False,
                "enable_sig_logg": False,
                "srl_log_path": str(ROOT_DIR / "runtime" / "logs" / "serial"),
                "sig_log_path": str(ROOT_DIR / "runtime" / "logs" / "serial_sig"),
            },
            "can_cfg": {
                "is_enable": True,
                "gate": "PCSIM",
                "can_speed_bps": 500000,
                "device_port": {
                    "host": self.ecu.udp.host,
                    "port": self.ecu.udp.port,
                    "node": self.ecu.udp.node,
                },
                "id_to_ignore": [],
                "enable_can_msg_logg": False,
                "can_log_path": str(ROOT_DIR / "runtime" / "logs" / "can"),
                "sig_log_path": str(ROOT_DIR / "runtime" / "logs" / "can_sig"),
            },
        }

    def _build_runtime_project_cfg(self) -> Path:
        cfg = self._load_base_cfg()
        cfg["signal_cfg"] = str(self.ecu.sym_file)

        can_cfg = cfg.get("can_cfg", {})
        if not isinstance(can_cfg, dict):
            can_cfg = {}
        can_cfg["is_enable"] = True
        can_cfg["gate"] = self.ecu.can_gate
        can_cfg["can_speed_bps"] = self.ecu.can_speed_bps

        if self.ecu.can_gate == "PCSIM":
            can_cfg["device_port"] = {
                "host": self.ecu.udp.host,
                "port": self.ecu.udp.port,
                "node": self.ecu.udp.node,
            }
        elif self.ecu.can_device_port is not None:
            can_cfg["device_port"] = self.ecu.can_device_port
        elif "device_port" not in can_cfg:
            can_cfg["device_port"] = ""

        if "id_to_ignore" not in can_cfg:
            can_cfg["id_to_ignore"] = []
        if "enable_can_msg_logg" not in can_cfg:
            can_cfg["enable_can_msg_logg"] = False

        # PCSIM tuning parameters (low-latency defaults, overridable from ecus_config.json)
        timeout_s = self.ecu.pcsim_timeout_s if self.ecu.pcsim_timeout_s is not None else self.ecu.udp.timeout_s
        poll_sleep_s = self.ecu.pcsim_poll_sleep_s if self.ecu.pcsim_poll_sleep_s is not None else 0.00005
        max_pop_per_cycle = self.ecu.pcsim_max_pop_per_cycle if self.ecu.pcsim_max_pop_per_cycle is not None else 128
        clear_on_connect = (
            self.ecu.pcsim_clear_can_tx_on_connect
            if self.ecu.pcsim_clear_can_tx_on_connect is not None
            else True
        )
        can_cfg["timeout_s"] = float(timeout_s)
        can_cfg["poll_sleep_s"] = float(poll_sleep_s)
        can_cfg["max_pop_per_cycle"] = int(max_pop_per_cycle)
        can_cfg["clear_can_tx_on_connect"] = bool(clear_on_connect)
        can_cfg["shared_can_nodes"] = [int(v) for v in self.ecu.pcsim_shared_can_nodes]
        can_cfg["rx_filters"] = [dict(v) for v in self.ecu.pcsim_rx_filters]

        runtime_root = ROOT_DIR / "runtime"
        runtime_logs = runtime_root / "logs" / self.ecu.name
        runtime_logs.mkdir(parents=True, exist_ok=True)
        can_cfg.setdefault("can_log_path", str(runtime_logs / "can"))
        can_cfg.setdefault("sig_log_path", str(runtime_logs / "can_sig"))
        cfg["can_cfg"] = can_cfg

        serial_cfg = cfg.get("serial_cfg", {})
        if not isinstance(serial_cfg, dict):
            serial_cfg = {}
        serial_cfg.setdefault("baudrate", 115200)
        serial_cfg.setdefault("port_com", "")
        serial_cfg.setdefault("frame_len", 0)
        serial_cfg.setdefault("is_enable", False)
        serial_cfg.setdefault("enable_srl_msg_logg", False)
        serial_cfg.setdefault("enable_sig_logg", False)
        serial_cfg.setdefault("srl_log_path", str(runtime_logs / "serial"))
        serial_cfg.setdefault("sig_log_path", str(runtime_logs / "serial_sig"))
        cfg["serial_cfg"] = serial_cfg

        runtime_root.mkdir(parents=True, exist_ok=True)
        out_cfg = runtime_root / f"{self.ecu.name}_prj_cfg.json"
        out_cfg.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return out_cfg

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.viewer is not None:
            try:
                if hasattr(self.viewer, "_persist_on_quit"):
                    self.viewer._persist_on_quit()
                self.viewer.kill_all_thread()
                self.viewer.close()
            except Exception:
                pass
        super().closeEvent(event)
