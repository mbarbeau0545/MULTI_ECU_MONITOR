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
    can_gate: str = "PCSIM"
    can_speed_bps: int = 250000
    can_device_port: Optional[Dict[str, Any]] = None


@dataclass
class MonitorConfig:
    mode: AppMode
    refresh_ms: int
    ecus: List[EcuConfig]
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

    if not cfg.ecus:
        errors.append("No ECU configured in 'ecus'")
        return errors, warnings

    allowed_can_gates = {"PCSIM", "PEAK", "WAVESHARE"}
    names_seen = set()
    pcsim_endpoints = set()

    for idx, ecu in enumerate(cfg.ecus):
        pfx = f"ecus[{idx}] ({ecu.name})"

        if not ecu.name.strip():
            errors.append(f"{pfx}: name is empty")
        if ecu.name in names_seen:
            errors.append(f"{pfx}: duplicate ECU name '{ecu.name}'")
        names_seen.add(ecu.name)

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

        if ecu.can_gate == "PCSIM":
            endpoint = (ecu.udp.host, ecu.udp.port)
            if endpoint in pcsim_endpoints:
                errors.append(f"{pfx}: duplicate PCSIM UDP endpoint {ecu.udp.host}:{ecu.udp.port}")
            pcsim_endpoints.add(endpoint)
        elif cfg.mode == AppMode.SIL:
            warnings.append(
                f"{pfx}: mode SIL with can_gate={ecu.can_gate}; I/O tab uses PCSIM UDP and may not match CAN transport"
            )

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

    ecus: List[EcuConfig] = []
    for raw in data.get("ecus", []):
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

        ecus.append(
            EcuConfig(
                name=str(raw.get("name", "ECU")),
                sym_file=_resolve(base, str(raw.get("sym_file", ""))),
                project_software_cfg=_resolve(base, str(raw.get("project_software_cfg", ""))),
                fmkio_config_public=_resolve(base, str(raw.get("fmkio_config_public", ""))),
                udp=udp,
                can_gate=str(raw.get("can_gate", "PCSIM")).upper(),
                can_speed_bps=int(raw.get("can_speed_bps", 500000)),
                can_device_port=can_device_port,
            )
        )

    cfg = MonitorConfig(mode=mode, refresh_ms=refresh_ms, ecus=ecus)
    errors, warnings = _validate_monitor_cfg(cfg)
    if errors:
        raise ConfigValidationError(errors, warnings)
    cfg.warnings = warnings
    return cfg
