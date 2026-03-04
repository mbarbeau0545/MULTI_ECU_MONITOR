import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from Protocole.CAN.Drivers.pcSim.pc_sim_client import PcSimClient

from .config import EcuConfig
from .fmkio_parser import parse_fmkio_counts

_PI = math.pi
_TWO_PI = 2.0 * math.pi
_MRAD_PER_RAD = 1000.0
_ECU_LINK_TIMEOUT_S = 5.0


def _to_int(text: str, default: int = 0) -> int:
    try:
        return int(text.strip(), 0)
    except Exception:
        return default


def _to_float(text: str, default: float = 0.0) -> float:
    try:
        return float(text.strip())
    except Exception:
        return default


def _wrap_to_pi(rad_value: float) -> float:
    wrapped = (rad_value + _PI) % _TWO_PI - _PI
    if wrapped <= -_PI:
        return _PI
    return wrapped


class PcSimIoTab(QWidget):
    def __init__(self, ecu: EcuConfig, refresh_ms: int = 200, cfg_path: Optional[Path] = None) -> None:
        super().__init__()
        self.ecu = ecu
        self.cfg_path = cfg_path
        self.client = PcSimClient(host=ecu.udp.host, port=ecu.udp.port, timeout=ecu.udp.timeout_s)
        self.counts = parse_fmkio_counts(ecu.fmkio_config_public)

        self.ana_edits: List[QLineEdit] = []
        self.pwm_edits: List[QLineEdit] = []
        self.pwm_freq_edits: List[QLineEdit] = []
        self.in_dig_edits: List[QLineEdit] = []
        self.out_dig_edits: List[QLineEdit] = []
        self.in_freq_edits: List[QLineEdit] = []
        self.enc_abs_edits: List[QLineEdit] = []
        self.enc_rel_edits: List[QLineEdit] = []
        self.enc_speed_edits: List[QLineEdit] = []
        self.enc_cfg_summary_lbls: Dict[int, QLabel] = {}

        self.encoder_mode_cfg: Dict[int, Dict[str, object]] = {}
        self.encoder_runtime_state: Dict[int, Dict[str, float]] = {}

        self.tick_lbl = QLabel("-")
        self.ecu_link_lbl = QLabel("ECU link: connecting...")
        self.ecu_link_lbl.setStyleSheet("color: #666;")
        self._ecu_online = False
        self._last_ecu_msg_ts = time.monotonic()
        self._offline_warned = False

        self._build_ui()
        self._load_encoder_modes_from_cfg()
        self._apply_encoder_mappings_to_runtime()

        self._enc_last_update_ts = time.monotonic()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_once)
        self.timer.start(max(50, refresh_ms))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("PC_SIM tick"))
        top.addWidget(self.tick_lbl)
        top.addWidget(self.ecu_link_lbl)
        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._refresh_once)
        top.addWidget(btn_refresh)
        top.addStretch(1)
        root.addLayout(top)

        split_top = QSplitter()
        split_top.addWidget(self._build_ana_group())
        split_top.addWidget(self._build_pwm_group())
        split_top.setSizes([500, 500])
        root.addWidget(split_top, 1)

        split_bottom = QSplitter()
        split_bottom.addWidget(self._build_in_dig_group())
        split_bottom.addWidget(self._build_out_dig_group())
        split_bottom.addWidget(self._build_in_freq_group())
        split_bottom.addWidget(self._build_encoder_group())
        split_bottom.setSizes([240, 240, 240, 700])
        root.addWidget(split_bottom, 1)

    def _build_ana_group(self) -> QWidget:
        g = QGroupBox("Analog")
        l = QGridLayout(g)
        for i in range(self.counts.get("ana", 0)):
            e = QLineEdit("0.0")
            bs = QPushButton("Set")
            bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_ana(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_ana(idx))
            l.addWidget(QLabel(f"ANA[{i}]"), i, 0)
            l.addWidget(e, i, 1)
            l.addWidget(bs, i, 2)
            l.addWidget(bg, i, 3)
            self.ana_edits.append(e)
        return self._wrap(g)

    def _build_pwm_group(self) -> QWidget:
        g = QGroupBox("PWM")
        l = QGridLayout(g)
        for i in range(self.counts.get("pwm", 0)):
            row = i * 2
            duty = QLineEdit("0")
            freq = QLineEdit("0.0")

            bsd = QPushButton("Set")
            bgd = QPushButton("Get")
            bsf = QPushButton("Set")
            bgf = QPushButton("Get")
            bsd.clicked.connect(lambda _=False, idx=i: self._set_pwm(idx))
            bgd.clicked.connect(lambda _=False, idx=i: self._get_pwm(idx))
            bsf.clicked.connect(lambda _=False, idx=i: self._set_pwm_freq(idx))
            bgf.clicked.connect(lambda _=False, idx=i: self._get_pwm_freq(idx))

            l.addWidget(QLabel(f"PWM[{i}] duty"), row, 0)
            l.addWidget(duty, row, 1)
            l.addWidget(bsd, row, 2)
            l.addWidget(bgd, row, 3)

            l.addWidget(QLabel("freq Hz"), row + 1, 0)
            l.addWidget(freq, row + 1, 1)
            l.addWidget(bsf, row + 1, 2)
            l.addWidget(bgf, row + 1, 3)

            self.pwm_edits.append(duty)
            self.pwm_freq_edits.append(freq)
        return self._wrap(g)

    def _build_in_dig_group(self) -> QWidget:
        g = QGroupBox("Input Dig")
        l = QGridLayout(g)
        for i in range(self.counts.get("in_dig", 0)):
            e = QLineEdit("0")
            bs = QPushButton("Set")
            bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_in_dig(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_in_dig(idx))
            l.addWidget(QLabel(f"IN_DIG[{i}]"), i, 0)
            l.addWidget(e, i, 1)
            l.addWidget(bs, i, 2)
            l.addWidget(bg, i, 3)
            self.in_dig_edits.append(e)
        return self._wrap(g)

    def _build_out_dig_group(self) -> QWidget:
        g = QGroupBox("Output Dig")
        l = QGridLayout(g)
        for i in range(self.counts.get("out_dig", 0)):
            e = QLineEdit("0")
            bs = QPushButton("Set")
            bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_out_dig(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_out_dig(idx))
            l.addWidget(QLabel(f"OUT_DIG[{i}]"), i, 0)
            l.addWidget(e, i, 1)
            l.addWidget(bs, i, 2)
            l.addWidget(bg, i, 3)
            self.out_dig_edits.append(e)
        return self._wrap(g)

    def _build_in_freq_group(self) -> QWidget:
        g = QGroupBox("Input Freq")
        l = QGridLayout(g)
        for i in range(self.counts.get("in_freq", 0)):
            e = QLineEdit("0.0")
            bs = QPushButton("Set")
            bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_in_freq(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_in_freq(idx))
            l.addWidget(QLabel(f"IN_FREQ[{i}]"), i, 0)
            l.addWidget(e, i, 1)
            l.addWidget(bs, i, 2)
            l.addWidget(bg, i, 3)
            self.in_freq_edits.append(e)
        return self._wrap(g)

    def _build_encoder_group(self) -> QWidget:
        g = QGroupBox("Encoder")
        l = QGridLayout(g)
        for i in range(self.counts.get("enc", 0)):
            row = i * 3

            a = QLineEdit("0.0")
            r = QLineEdit("0.0")
            s = QLineEdit("0.0")
            bsp = QPushButton("Set Pos")
            bgp = QPushButton("Get Pos")
            bss = QPushButton("Set Spd")
            bgs = QPushButton("Get Spd")
            bcfg = QPushButton(f"Cfg ENC[{i}]")
            summary = QLabel("-")

            bsp.clicked.connect(lambda _=False, idx=i: self._set_enc_pos(idx))
            bgp.clicked.connect(lambda _=False, idx=i: self._get_enc_pos(idx))
            bss.clicked.connect(lambda _=False, idx=i: self._set_enc_speed(idx))
            bgs.clicked.connect(lambda _=False, idx=i: self._get_enc_speed(idx))
            bcfg.clicked.connect(lambda _=False, idx=i: self._open_encoder_cfg_dialog(idx))

            l.addWidget(QLabel(f"ENC[{i}] abs/rel"), row, 0)
            l.addWidget(a, row, 1)
            l.addWidget(r, row, 2)
            l.addWidget(bsp, row, 3)
            l.addWidget(bgp, row, 4)

            l.addWidget(QLabel("speed"), row + 1, 0)
            l.addWidget(s, row + 1, 1)
            l.addWidget(bss, row + 1, 3)
            l.addWidget(bgs, row + 1, 4)

            l.addWidget(bcfg, row + 2, 0, 1, 2)
            l.addWidget(summary, row + 2, 2, 1, 3)

            self.enc_abs_edits.append(a)
            self.enc_rel_edits.append(r)
            self.enc_speed_edits.append(s)
            self.enc_cfg_summary_lbls[i] = summary
            self.encoder_runtime_state[i] = {"pos": 0.0, "dir": 1.0, "time_s": 0.0}

        return self._wrap(g)

    @staticmethod
    def _wrap(widget: QWidget) -> QScrollArea:
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setWidget(widget)
        return s

    def _refresh_once(self) -> None:
        now_s = time.monotonic()
        got_reply = False
        try:
            parts = self.client.get_all().split()
            got_reply = True
            if "TICK" in parts:
                self.tick_lbl.setText(parts[parts.index("TICK") + 1])
            if "ANA" in parts and "PWM" in parts:
                ia = parts.index("ANA")
                ip = parts.index("PWM")
                ana = parts[ia + 1 : ip]
                pwm = parts[ip + 1 :]
                for i in range(min(len(self.ana_edits), len(ana))):
                    self._set_text_if_not_editing(self.ana_edits[i], ana[i])
                for i in range(min(len(self.pwm_edits), len(pwm))):
                    self._set_text_if_not_editing(self.pwm_edits[i], pwm[i])
        except Exception:
            pass

        if got_reply:
            self._last_ecu_msg_ts = now_s
            if not self._ecu_online:
                self._ecu_online = True
                self._offline_warned = False
                self.ecu_link_lbl.setText("ECU link: online")
                self.ecu_link_lbl.setStyleSheet("color: #008000;")
                self._on_ecu_reconnected()
        elif (now_s - self._last_ecu_msg_ts) >= _ECU_LINK_TIMEOUT_S:
            if self._ecu_online:
                self._ecu_online = False
            self.ecu_link_lbl.setText("ECU link: offline (no reply > 5s)")
            self.ecu_link_lbl.setStyleSheet("color: #b00020;")
            if not self._offline_warned:
                print(f"[WARNING] [{self.ecu.name}] ECU link timeout (> {_ECU_LINK_TIMEOUT_S:.1f}s without reply)")
                self._offline_warned = True

        self._step_encoder_modes()

    def _on_ecu_reconnected(self) -> None:
        self._apply_encoder_mappings_to_runtime()
        for idx in range(self.counts.get("enc", 0)):
            cfg = self._default_encoder_mode_cfg(idx)
            cfg.update(self.encoder_mode_cfg.get(idx, {}))
            mode = str(cfg.get("mode", "manual"))
            if mode in ("manual", "encdr_based_pulse"):
                continue
            pos_rad = _wrap_to_pi(float(self.encoder_runtime_state[idx].get("pos", 0.0)))
            speed_rad_s = _to_float(self.enc_speed_edits[idx].text(), 0.0)
            try:
                self.client.set_enc_pos(idx, pos_rad * _MRAD_PER_RAD, pos_rad * _MRAD_PER_RAD)
                self.client.set_enc_speed(idx, speed_rad_s * _MRAD_PER_RAD)
            except Exception:
                pass
        print(f"[INFO] [{self.ecu.name}] ECU reconnected, encoder mapping reapplied")

    @staticmethod
    def _set_text_if_not_editing(edit: QLineEdit, value: str) -> None:
        if edit.hasFocus():
            return
        if edit.text() != value:
            edit.setText(value)

    def _step_encoder_modes(self) -> None:
        now = time.monotonic()
        dt = now - self._enc_last_update_ts
        self._enc_last_update_ts = now
        if dt <= 0.0:
            return

        for idx, cfg in self.encoder_mode_cfg.items():
            mode = str(cfg.get("mode", "manual"))
            state = self.encoder_runtime_state[idx]

            if mode == "manual":
                continue

            if mode == "encdr_based_pulse":
                try:
                    abs_mrad, rel_mrad = self.client.get_enc_pos(idx)
                    speed_mrad_s = self.client.get_enc_speed(idx)
                    abs_rad = _wrap_to_pi(abs_mrad / _MRAD_PER_RAD)
                    rel_rad = _wrap_to_pi(rel_mrad / _MRAD_PER_RAD)
                    speed_rad_s = speed_mrad_s / _MRAD_PER_RAD
                    self._set_text_if_not_editing(self.enc_abs_edits[idx], f"{abs_rad:.6f}")
                    self._set_text_if_not_editing(self.enc_rel_edits[idx], f"{rel_rad:.6f}")
                    self._set_text_if_not_editing(self.enc_speed_edits[idx], f"{speed_rad_s:.6f}")
                    self.encoder_runtime_state[idx]["pos"] = rel_rad
                except Exception:
                    pass
                continue

            pos = state["pos"]
            speed = 0.0

            if mode == "constant_speed":
                speed = float(cfg.get("constant_speed", 0.0))
                pos += speed * dt
            elif mode == "ramp":
                vmin = float(cfg.get("ramp_min", -1000.0))
                vmax = float(cfg.get("ramp_max", 1000.0))
                rate = abs(float(cfg.get("ramp_rate", 200.0)))
                if vmax < vmin:
                    vmin, vmax = vmax, vmin
                speed = rate * state["dir"]
                pos += speed * dt
                if pos >= vmax:
                    pos = vmax
                    state["dir"] = -1.0
                elif pos <= vmin:
                    pos = vmin
                    state["dir"] = 1.0
                speed = rate * state["dir"]
            elif mode == "sinusoidal":
                amp = float(cfg.get("sin_amp", 500.0))
                offs = float(cfg.get("sin_offset", 0.0))
                period = max(0.05, float(cfg.get("sin_period_s", 4.0)))
                state["time_s"] += dt
                omega = (2.0 * math.pi) / period
                pos = offs + amp * math.sin(omega * state["time_s"])
                speed = amp * omega * math.cos(omega * state["time_s"])

            pos = _wrap_to_pi(pos)
            state["pos"] = pos

            try:
                self.client.set_enc_pos(idx, pos * _MRAD_PER_RAD, pos * _MRAD_PER_RAD)
                self.client.set_enc_speed(idx, speed * _MRAD_PER_RAD)
                self._set_text_if_not_editing(self.enc_abs_edits[idx], f"{pos:.6f}")
                self._set_text_if_not_editing(self.enc_rel_edits[idx], f"{pos:.6f}")
                self._set_text_if_not_editing(self.enc_speed_edits[idx], f"{speed:.6f}")
            except Exception:
                pass

    def _default_encoder_mode_cfg(self, idx: int) -> Dict[str, object]:
        return {
            "idx": idx,
            "mode": "manual",
            "constant_speed": 0.0,
            "ramp_min": -1000.0,
            "ramp_max": 1000.0,
            "ramp_rate": 200.0,
            "sin_amp": 500.0,
            "sin_offset": 0.0,
            "sin_period_s": 4.0,
            "sig_pwm": idx,
            "sig_dir": idx,
            "pulses_per_revolution": 3200.0,
        }

    def _load_encoder_modes_from_cfg(self) -> None:
        by_idx: Dict[int, Dict[str, object]] = {}
        for raw in self.ecu.encoder_modes:
            if not isinstance(raw, dict):
                continue
            idx = int(raw.get("idx", -1))
            if idx < 0:
                continue
            by_idx[idx] = raw

        for idx in range(self.counts.get("enc", 0)):
            cfg = self._default_encoder_mode_cfg(idx)
            cfg.update(by_idx.get(idx, {}))
            self.encoder_mode_cfg[idx] = cfg
            self._refresh_encoder_cfg_summary(idx)

    def _refresh_encoder_cfg_summary(self, idx: int) -> None:
        cfg = self.encoder_mode_cfg.get(idx, self._default_encoder_mode_cfg(idx))
        mode = str(cfg.get("mode", "manual"))
        if mode == "encdr_based_pulse":
            text = (
                f"mode={mode} pwm={cfg.get('sig_pwm', idx)} dir={cfg.get('sig_dir', idx)} "
                f"ppr={cfg.get('pulses_per_revolution', 3200.0)}"
            )
        else:
            text = f"mode={mode}"
        lbl = self.enc_cfg_summary_lbls.get(idx)
        if lbl is not None:
            lbl.setText(text)

    def _collect_encoder_modes(self) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        for idx in range(self.counts.get("enc", 0)):
            cfg = self._default_encoder_mode_cfg(idx)
            cfg.update(self.encoder_mode_cfg.get(idx, {}))
            out.append(cfg)
        return out

    def _read_json_data(self) -> Dict[str, Any]:
        if self.cfg_path is None:
            raise RuntimeError("No config path")
        return json.loads(self.cfg_path.read_text(encoding="utf-8-sig"))

    def _find_ecu_entry(self, data: Dict[str, Any]) -> Dict[str, Any]:
        ecus = data.get("ecus", [])
        for ecu in ecus:
            if isinstance(ecu, dict) and str(ecu.get("name", "")) == self.ecu.name:
                return ecu
        raise RuntimeError(f"ECU '{self.ecu.name}' not found in {self.cfg_path}")

    def _save_encoder_modes_to_json(self) -> None:
        if self.cfg_path is None:
            raise RuntimeError("No config path")
        data = self._read_json_data()
        target = self._find_ecu_entry(data)
        target["encoder_modes"] = self._collect_encoder_modes()
        self.cfg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.ecu.encoder_modes = list(target["encoder_modes"])

    def _apply_encoder_mappings_to_runtime(self) -> None:
        for idx in range(self.counts.get("enc", 0)):
            cfg = self._default_encoder_mode_cfg(idx)
            cfg.update(self.encoder_mode_cfg.get(idx, {}))
            sig_pwm = int(cfg.get("sig_pwm", idx))
            sig_dir = int(cfg.get("sig_dir", idx))
            ppr = float(cfg.get("pulses_per_revolution", 3200.0))
            try:
                self.client.set_enc_map(idx, sig_pwm, ppr, sig_dir)
            except Exception:
                pass

    def _open_encoder_cfg_dialog(self, idx: int) -> None:
        current = self._default_encoder_mode_cfg(idx)
        current.update(self.encoder_mode_cfg.get(idx, {}))

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Encoder Config ENC[{idx}]")
        layout = QGridLayout(dlg)

        mode = QComboBox()
        mode.addItems(["manual", "constant_speed", "ramp", "sinusoidal", "encdr_based_pulse"])
        constant_speed = QLineEdit(str(current.get("constant_speed", 0.0)))
        ramp_min = QLineEdit(str(current.get("ramp_min", -1000.0)))
        ramp_max = QLineEdit(str(current.get("ramp_max", 1000.0)))
        ramp_rate = QLineEdit(str(current.get("ramp_rate", 200.0)))
        sin_amp = QLineEdit(str(current.get("sin_amp", 500.0)))
        sin_offset = QLineEdit(str(current.get("sin_offset", 0.0)))
        sin_period = QLineEdit(str(current.get("sin_period_s", 4.0)))
        sig_pwm = QLineEdit(str(current.get("sig_pwm", idx)))
        sig_dir = QLineEdit(str(current.get("sig_dir", idx)))
        ppr = QLineEdit(str(current.get("pulses_per_revolution", 3200.0)))

        found = mode.findText(str(current.get("mode", "manual")))
        mode.setCurrentIndex(found if found >= 0 else 0)

        layout.addWidget(QLabel("mode"), 0, 0)
        layout.addWidget(mode, 0, 1, 1, 2)
        layout.addWidget(QLabel("constant_speed"), 1, 0)
        layout.addWidget(constant_speed, 1, 1, 1, 2)
        layout.addWidget(QLabel("ramp_min"), 2, 0)
        layout.addWidget(ramp_min, 2, 1)
        layout.addWidget(QLabel("ramp_max"), 2, 2)
        layout.addWidget(ramp_max, 2, 3)
        layout.addWidget(QLabel("ramp_rate"), 3, 0)
        layout.addWidget(ramp_rate, 3, 1, 1, 2)
        layout.addWidget(QLabel("sin_amp"), 4, 0)
        layout.addWidget(sin_amp, 4, 1)
        layout.addWidget(QLabel("sin_offset"), 4, 2)
        layout.addWidget(sin_offset, 4, 3)
        layout.addWidget(QLabel("sin_period_s"), 5, 0)
        layout.addWidget(sin_period, 5, 1, 1, 2)
        layout.addWidget(QLabel("sig_pwm"), 6, 0)
        layout.addWidget(sig_pwm, 6, 1)
        layout.addWidget(QLabel("sig_dir"), 6, 2)
        layout.addWidget(sig_dir, 6, 3)
        layout.addWidget(QLabel("pulses_per_revolution"), 7, 0)
        layout.addWidget(ppr, 7, 1, 1, 3)

        btn_save = QPushButton("Save")
        btn_reset = QPushButton("Reset Default")
        btn_cancel = QPushButton("Cancel")
        layout.addWidget(btn_save, 8, 1)
        layout.addWidget(btn_reset, 8, 2)
        layout.addWidget(btn_cancel, 8, 3)

        def build_cfg() -> Dict[str, object]:
            return {
                "idx": idx,
                "mode": str(mode.currentText()),
                "constant_speed": _to_float(constant_speed.text(), 0.0),
                "ramp_min": _to_float(ramp_min.text(), -1000.0),
                "ramp_max": _to_float(ramp_max.text(), 1000.0),
                "ramp_rate": _to_float(ramp_rate.text(), 200.0),
                "sin_amp": _to_float(sin_amp.text(), 500.0),
                "sin_offset": _to_float(sin_offset.text(), 0.0),
                "sin_period_s": _to_float(sin_period.text(), 4.0),
                "sig_pwm": _to_int(sig_pwm.text(), idx),
                "sig_dir": _to_int(sig_dir.text(), idx),
                "pulses_per_revolution": _to_float(ppr.text(), 3200.0),
            }

        def apply_cfg_to_widgets(cfg: Dict[str, object]) -> None:
            found_mode = mode.findText(str(cfg.get("mode", "manual")))
            mode.setCurrentIndex(found_mode if found_mode >= 0 else 0)
            constant_speed.setText(str(cfg.get("constant_speed", 0.0)))
            ramp_min.setText(str(cfg.get("ramp_min", -1000.0)))
            ramp_max.setText(str(cfg.get("ramp_max", 1000.0)))
            ramp_rate.setText(str(cfg.get("ramp_rate", 200.0)))
            sin_amp.setText(str(cfg.get("sin_amp", 500.0)))
            sin_offset.setText(str(cfg.get("sin_offset", 0.0)))
            sin_period.setText(str(cfg.get("sin_period_s", 4.0)))
            sig_pwm.setText(str(cfg.get("sig_pwm", idx)))
            sig_dir.setText(str(cfg.get("sig_dir", idx)))
            ppr.setText(str(cfg.get("pulses_per_revolution", 3200.0)))

        def on_save() -> None:
            try:
                self.encoder_mode_cfg[idx] = build_cfg()
                self._refresh_encoder_cfg_summary(idx)
                self._save_encoder_modes_to_json()
                self._apply_encoder_mappings_to_runtime()
                dlg.accept()
            except Exception as exc:
                QMessageBox.warning(self, "Encoder Config", str(exc))

        def on_reset() -> None:
            try:
                cfg = self._default_encoder_mode_cfg(idx)
                self.encoder_mode_cfg[idx] = cfg
                apply_cfg_to_widgets(cfg)
                self._refresh_encoder_cfg_summary(idx)
                self._save_encoder_modes_to_json()
                self._apply_encoder_mappings_to_runtime()
                dlg.accept()
            except Exception as exc:
                QMessageBox.warning(self, "Encoder Config", str(exc))

        btn_save.clicked.connect(on_save)
        btn_reset.clicked.connect(on_reset)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.exec_()

    def _set_ana(self, i: int) -> None:
        self.client.set_ana(i, _to_float(self.ana_edits[i].text(), 0.0))

    def _get_ana(self, i: int) -> None:
        self.ana_edits[i].setText(f"{self.client.get_ana(i)}")

    def _set_pwm(self, i: int) -> None:
        self.client.set_pwm(i, _to_int(self.pwm_edits[i].text(), 0))

    def _get_pwm(self, i: int) -> None:
        self.pwm_edits[i].setText(f"{self.client.get_pwm(i)}")

    def _set_pwm_freq(self, i: int) -> None:
        self.client.set_pwm_freq(i, _to_float(self.pwm_freq_edits[i].text(), 0.0))

    def _get_pwm_freq(self, i: int) -> None:
        self.pwm_freq_edits[i].setText(f"{self.client.get_pwm_freq(i)}")

    def _set_in_dig(self, i: int) -> None:
        self.client.set_in_dig(i, _to_int(self.in_dig_edits[i].text(), 0))

    def _get_in_dig(self, i: int) -> None:
        self.in_dig_edits[i].setText(str(self.client.get_in_dig(i)))

    def _set_out_dig(self, i: int) -> None:
        self.client.set_out_dig(i, _to_int(self.out_dig_edits[i].text(), 0))

    def _get_out_dig(self, i: int) -> None:
        self.out_dig_edits[i].setText(str(self.client.get_out_dig(i)))

    def _set_in_freq(self, i: int) -> None:
        self.client.set_in_freq(i, _to_float(self.in_freq_edits[i].text(), 0.0))

    def _get_in_freq(self, i: int) -> None:
        self.in_freq_edits[i].setText(f"{self.client.get_in_freq(i)}")

    def _force_encoder_manual_mode(self, i: int) -> None:
        cfg = self._default_encoder_mode_cfg(i)
        cfg.update(self.encoder_mode_cfg.get(i, {}))
        mode = str(cfg.get("mode", "manual"))
        if mode != "manual":
            cfg["mode"] = "manual"
            self.encoder_mode_cfg[i] = cfg
            self._refresh_encoder_cfg_summary(i)
            print(f"[INFO] [{self.ecu.name}] ENC[{i}] switched to manual mode after direct set")

    def _set_enc_pos(self, i: int) -> None:
        self._force_encoder_manual_mode(i)
        abs_rad = _wrap_to_pi(_to_float(self.enc_abs_edits[i].text(), 0.0))
        rel_rad = _wrap_to_pi(_to_float(self.enc_rel_edits[i].text(), 0.0))
        self.client.set_enc_pos(i, abs_rad * _MRAD_PER_RAD, rel_rad * _MRAD_PER_RAD)
        self.encoder_runtime_state[i]["pos"] = rel_rad
        self.enc_abs_edits[i].setText(f"{abs_rad:.6f}")
        self.enc_rel_edits[i].setText(f"{rel_rad:.6f}")

    def _get_enc_pos(self, i: int) -> None:
        abs_mrad, rel_mrad = self.client.get_enc_pos(i)
        abs_rad = _wrap_to_pi(abs_mrad / _MRAD_PER_RAD)
        rel_rad = _wrap_to_pi(rel_mrad / _MRAD_PER_RAD)
        self.enc_abs_edits[i].setText(f"{abs_rad:.6f}")
        self.enc_rel_edits[i].setText(f"{rel_rad:.6f}")
        self.encoder_runtime_state[i]["pos"] = rel_rad

    def _set_enc_speed(self, i: int) -> None:
        self._force_encoder_manual_mode(i)
        speed_rad_s = _to_float(self.enc_speed_edits[i].text(), 0.0)
        self.client.set_enc_speed(i, speed_rad_s * _MRAD_PER_RAD)
        self.enc_speed_edits[i].setText(f"{speed_rad_s:.6f}")

    def _get_enc_speed(self, i: int) -> None:
        speed_mrad_s = self.client.get_enc_speed(i)
        self.enc_speed_edits[i].setText(f"{(speed_mrad_s / _MRAD_PER_RAD):.6f}")
