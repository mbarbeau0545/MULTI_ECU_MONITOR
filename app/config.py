import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class AppMode(str, Enum):
    SIL = "SIL"
    HIL = "HIL"


@dataclass
class UdpConfig:
    host: str = "127.0.0.1"
    port: int = 19090
    timeout_s: float = 0.4
    node: int = 0


@dataclass
class EcuConfig:
    name: str
    sym_file: Path
    project_software_cfg: Path
    fmkio_config_public: Path
    udp: UdpConfig
    enable_ecu: bool = True
    ecu_in_debug: bool = False
    can_gate: str = "PCSIM"
    can_speed_bps: int = 250000
    can_device_port: Optional[Dict[str, Any]] = None
    pcsim_timeout_s: Optional[float] = None
    pcsim_poll_sleep_s: Optional[float] = None
    pcsim_max_pop_per_cycle: Optional[int] = None
    pcsim_clear_can_tx_on_connect: Optional[bool] = None
    pcsim_shared_can_nodes: List[int] = field(default_factory=list)
    pcsim_rx_filters: List[Dict[str, Any]] = field(default_factory=list)
    encoder_modes: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MonitorConfig:
    mode: AppMode
    refresh_ms: int
    ecus: List[EcuConfig]
    can_broker_enabled: bool = False
    can_broker_control_port: int = 19600
    can_broker_poll_sleep_s: float = 0.001
    can_broker_max_pop_per_ecu: int = 128
    can_broker_max_inject_per_cycle: int = 2048
    warnings: List[str] = field(default_factory=list)


class ConfigValidationError(Exception):
    def __init__(self, errors: List[str], warnings: Optional[List[str]] = None) -> None:
        self.errors = errors
        self.warnings = warnings or []
        message = "Invalid multi_ecu_monitor config:\n" + "\n".join(f"- {e}" for e in errors)
        if self.warnings:
            message += "\nWarnings:\n" + "\n".join(f"- {w}" for w in self.warnings)
        super().__init__(message)


def _resolve(base: Path, value: str) -> Path:
    p = Path(value)
    if p.is_absolute():
        return p
    return (base / p).resolve()


def _validate_monitor_cfg(cfg: MonitorConfig) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if cfg.refresh_ms < 20:
        warnings.append(f"refresh_ms={cfg.refresh_ms} is very low; recommended >= 50 ms")
    if cfg.refresh_ms > 5000:
        warnings.append(f"refresh_ms={cfg.refresh_ms} is high; UI may look frozen")
    if cfg.can_broker_poll_sleep_s < 0.0:
        errors.append("general.can_broker.poll_sleep_s must be >= 0")
    if cfg.can_broker_control_port < 1 or cfg.can_broker_control_port > 65535:
        errors.append("general.can_broker.control_port must be in [1..65535]")
    if cfg.can_broker_max_pop_per_ecu < 1:
        errors.append("general.can_broker.max_pop_per_ecu must be >= 1")
    if cfg.can_broker_max_inject_per_cycle < 1:
        errors.append("general.can_broker.max_inject_per_cycle must be >= 1")

    if not cfg.ecus:
        warnings.append("No active ECU in 'ecus' (enable_ecu=false and ecu_in_debug=false for all)")
        return errors, warnings

    allowed_can_gates = {"PCSIM", "PEAK", "WAVESHARE"}
    names_seen = set()
    pcsim_endpoints = set()
    pcsim_enabled_count = 0

    for idx, ecu in enumerate(cfg.ecus):
        pfx = f"ecus[{idx}] ({ecu.name})"

        if not ecu.name.strip():
            errors.append(f"{pfx}: name is empty")
        if ecu.name in names_seen:
            errors.append(f"{pfx}: duplicate ECU name '{ecu.name}'")
        names_seen.add(ecu.name)
        if ecu.enable_ecu and ecu.ecu_in_debug:
            errors.append(f"{pfx}: enable_ecu and ecu_in_debug cannot both be true")

        if not ecu.sym_file.exists():
            errors.append(f"{pfx}: sym_file does not exist: {ecu.sym_file}")
        elif ecu.sym_file.suffix.lower() != ".sym":
            warnings.append(f"{pfx}: sym_file extension is not .sym ({ecu.sym_file.name})")

        if not ecu.project_software_cfg.exists():
            errors.append(f"{pfx}: project_software_cfg does not exist: {ecu.project_software_cfg}")

        if not ecu.fmkio_config_public.exists():
            errors.append(f"{pfx}: fmkio_config_public does not exist: {ecu.fmkio_config_public}")

        if not ecu.udp.host.strip():
            errors.append(f"{pfx}: udp.host is empty")
        if ecu.udp.port < 1 or ecu.udp.port > 65535:
            errors.append(f"{pfx}: udp.port out of range [1..65535]: {ecu.udp.port}")
        if ecu.udp.timeout_s <= 0.0:
            errors.append(f"{pfx}: udp.timeout_s must be > 0")
        if ecu.udp.node < 0:
            errors.append(f"{pfx}: udp.node must be >= 0")

        if ecu.can_gate not in allowed_can_gates:
            errors.append(f"{pfx}: can_gate '{ecu.can_gate}' invalid (allowed: {sorted(allowed_can_gates)})")

        if ecu.can_speed_bps <= 0:
            errors.append(f"{pfx}: can_speed_bps must be > 0")

        if ecu.pcsim_timeout_s is not None and ecu.pcsim_timeout_s <= 0.0:
            errors.append(f"{pfx}: pcsim_timeout_s must be > 0")
        if ecu.pcsim_poll_sleep_s is not None and ecu.pcsim_poll_sleep_s < 0.0:
            errors.append(f"{pfx}: pcsim_poll_sleep_s must be >= 0")
        if ecu.pcsim_max_pop_per_cycle is not None and ecu.pcsim_max_pop_per_cycle < 1:
            errors.append(f"{pfx}: pcsim_max_pop_per_cycle must be >= 1")
        for node in ecu.pcsim_shared_can_nodes:
            if int(node) < 0:
                errors.append(f"{pfx}: pcsim_shared_can_nodes contains invalid node {node}")
                break

        if ecu.can_gate == "PCSIM":
            pcsim_enabled_count += 1
            endpoint = (ecu.udp.host, ecu.udp.port)
            if endpoint in pcsim_endpoints:
                errors.append(f"{pfx}: duplicate PCSIM UDP endpoint {ecu.udp.host}:{ecu.udp.port}")
            pcsim_endpoints.add(endpoint)
        elif cfg.mode == AppMode.SIL:
            warnings.append(
                f"{pfx}: mode SIL with can_gate={ecu.can_gate}; I/O tab uses PCSIM UDP and may not match CAN transport"
            )

    if cfg.can_broker_enabled and pcsim_enabled_count < 2:
        warnings.append("general.can_broker.enabled=true but fewer than 2 PCSIM ECUs are enabled")

    return errors, warnings


def load_config(cfg_path: Path) -> MonitorConfig:
    if not cfg_path.exists():
        raise ConfigValidationError([f"Config file not found: {cfg_path}"])

    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ConfigValidationError([f"Invalid JSON in {cfg_path}: {exc}"]) from exc

    # Resolve relative paths from the process working directory.
    # This allows launching the monitor from the project root with
    # config entries like "Doc/...".
    base = Path.cwd().resolve()

    general = data.get("general", {}) if isinstance(data, dict) else {}
    mode_raw = str(general.get("mode", "SIL")).upper()
    if mode_raw not in (AppMode.SIL.value, AppMode.HIL.value):
        raise ConfigValidationError([f"general.mode '{mode_raw}' invalid (expected SIL or HIL)"])
    mode = AppMode(mode_raw)
    refresh_ms = int(general.get("refresh_ms", 200))
    can_broker_raw = general.get("can_broker", {})
    if not isinstance(can_broker_raw, dict):
        can_broker_raw = {}

    def _as_bool(value: Any, default: bool = True) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("1", "true", "yes", "on"):
                return True
            if lowered in ("0", "false", "no", "off"):
                return False
        return default

    ecus: List[EcuConfig] = []
    for raw in data.get("ecus", []):
        if not isinstance(raw, dict):
            continue
        enabled = _as_bool(raw.get("enable_ecu", True), True)
        in_debug = _as_bool(raw.get("ecu_in_debug", False), False)
        if (not enabled) and (not in_debug):
            continue

        udp_raw = raw.get("udp", {}) if isinstance(raw, dict) else {}
        udp = UdpConfig(
            host=str(udp_raw.get("host", "127.0.0.1")),
            port=int(udp_raw.get("port", 19090)),
            timeout_s=float(udp_raw.get("timeout_s", 0.4)),
            node=int(udp_raw.get("node", 0)),
        )
        can_device = raw.get("can_device_port")
        if isinstance(can_device, dict):
            can_device_port = dict(can_device)
        else:
            can_device_port = None
        pcsim_can = raw.get("pcsim_can")
        if not isinstance(pcsim_can, dict):
            pcsim_can = {}
        shared_nodes_raw = pcsim_can.get("shared_can_nodes", [])
        if isinstance(shared_nodes_raw, list):
            shared_nodes = [int(v) for v in shared_nodes_raw]
        else:
            shared_nodes = []
        rx_filters_raw = pcsim_can.get("rx_filters", [])
        if not isinstance(rx_filters_raw, list):
            rx_filters_raw = []

        ecus.append(
            EcuConfig(
                name=str(raw.get("name", "ECU")),
                sym_file=_resolve(base, str(raw.get("sym_file", ""))),
                project_software_cfg=_resolve(base, str(raw.get("project_software_cfg", ""))),
                fmkio_config_public=_resolve(base, str(raw.get("fmkio_config_public", ""))),
                udp=udp,
                enable_ecu=enabled,
                ecu_in_debug=in_debug,
                encoder_modes=list(raw.get("encoder_modes", [])) if isinstance(raw.get("encoder_modes"), list) else [],
                can_gate=str(raw.get("can_gate", "PCSIM")).upper(),
                can_speed_bps=int(raw.get("can_speed_bps", 500000)),
                can_device_port=can_device_port,
                pcsim_timeout_s=float(pcsim_can["timeout_s"]) if "timeout_s" in pcsim_can else None,
                pcsim_poll_sleep_s=float(pcsim_can["poll_sleep_s"]) if "poll_sleep_s" in pcsim_can else None,
                pcsim_max_pop_per_cycle=int(pcsim_can["max_pop_per_cycle"]) if "max_pop_per_cycle" in pcsim_can else None,
                pcsim_clear_can_tx_on_connect=_as_bool(pcsim_can.get("clear_can_tx_on_connect"), True)
                if "clear_can_tx_on_connect" in pcsim_can
                else None,
                pcsim_shared_can_nodes=shared_nodes,
                pcsim_rx_filters=[dict(v) for v in rx_filters_raw if isinstance(v, dict)],
            )
        )

    cfg = MonitorConfig(
        mode=mode,
        refresh_ms=refresh_ms,
        ecus=ecus,
        can_broker_enabled=_as_bool(can_broker_raw.get("enabled", False), False),
        can_broker_control_port=int(can_broker_raw.get("control_port", 19600)),
        can_broker_poll_sleep_s=float(can_broker_raw.get("poll_sleep_s", 0.001)),
        can_broker_max_pop_per_ecu=max(1, int(can_broker_raw.get("max_pop_per_ecu", 128))),
        can_broker_max_inject_per_cycle=max(1, int(can_broker_raw.get("max_inject_per_cycle", 2048))),
    )
    errors, warnings = _validate_monitor_cfg(cfg)
    if errors:
        raise ConfigValidationError(errors, warnings)
    cfg.warnings = warnings
    return cfg
