from typing import List

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from Protocole.CAN.Drivers.pcSim.pc_sim_client import PcSimClient

from .config import EcuConfig
from .fmkio_parser import parse_fmkio_counts


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


class PcSimIoTab(QWidget):
    def __init__(self, ecu: EcuConfig, refresh_ms: int = 200) -> None:
        super().__init__()
        self.ecu = ecu
        self.client = PcSimClient(host=ecu.udp.host, port=ecu.udp.port, timeout=ecu.udp.timeout_s)
        self.counts = parse_fmkio_counts(ecu.fmkio_config_public)

        self.ana_edits: List[QLineEdit] = []
        self.pwm_edits: List[QLineEdit] = []
        self.in_dig_edits: List[QLineEdit] = []
        self.out_dig_edits: List[QLineEdit] = []
        self.in_freq_edits: List[QLineEdit] = []
        self.enc_abs_edits: List[QLineEdit] = []
        self.enc_rel_edits: List[QLineEdit] = []
        self.enc_speed_edits: List[QLineEdit] = []

        self.tick_lbl = QLabel("-")

        self._build_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh_once)
        self.timer.start(max(50, refresh_ms))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("PC_SIM tick"))
        top.addWidget(self.tick_lbl)
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
        split_bottom.setSizes([260, 260, 260, 360])
        root.addWidget(split_bottom, 1)

    def _build_ana_group(self) -> QWidget:
        g = QGroupBox("Analog")
        l = QGridLayout(g)
        for i in range(self.counts.get("ana", 0)):
            e = QLineEdit("0.0")
            bs = QPushButton("Set"); bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_ana(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_ana(idx))
            l.addWidget(QLabel(f"ANA[{i}]"), i, 0)
            l.addWidget(e, i, 1); l.addWidget(bs, i, 2); l.addWidget(bg, i, 3)
            self.ana_edits.append(e)
        return self._wrap(g)

    def _build_pwm_group(self) -> QWidget:
        g = QGroupBox("PWM")
        l = QGridLayout(g)
        for i in range(self.counts.get("pwm", 0)):
            e = QLineEdit("0")
            bs = QPushButton("Set"); bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_pwm(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_pwm(idx))
            l.addWidget(QLabel(f"PWM[{i}]"), i, 0)
            l.addWidget(e, i, 1); l.addWidget(bs, i, 2); l.addWidget(bg, i, 3)
            self.pwm_edits.append(e)
        return self._wrap(g)

    def _build_in_dig_group(self) -> QWidget:
        g = QGroupBox("Input Dig")
        l = QGridLayout(g)
        for i in range(self.counts.get("in_dig", 0)):
            e = QLineEdit("0")
            bs = QPushButton("Set"); bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_in_dig(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_in_dig(idx))
            l.addWidget(QLabel(f"IN_DIG[{i}]"), i, 0)
            l.addWidget(e, i, 1); l.addWidget(bs, i, 2); l.addWidget(bg, i, 3)
            self.in_dig_edits.append(e)
        return self._wrap(g)

    def _build_out_dig_group(self) -> QWidget:
        g = QGroupBox("Output Dig")
        l = QGridLayout(g)
        for i in range(self.counts.get("out_dig", 0)):
            e = QLineEdit("0")
            bs = QPushButton("Set"); bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_out_dig(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_out_dig(idx))
            l.addWidget(QLabel(f"OUT_DIG[{i}]"), i, 0)
            l.addWidget(e, i, 1); l.addWidget(bs, i, 2); l.addWidget(bg, i, 3)
            self.out_dig_edits.append(e)
        return self._wrap(g)

    def _build_in_freq_group(self) -> QWidget:
        g = QGroupBox("Input Freq")
        l = QGridLayout(g)
        for i in range(self.counts.get("in_freq", 0)):
            e = QLineEdit("0.0")
            bs = QPushButton("Set"); bg = QPushButton("Get")
            bs.clicked.connect(lambda _=False, idx=i: self._set_in_freq(idx))
            bg.clicked.connect(lambda _=False, idx=i: self._get_in_freq(idx))
            l.addWidget(QLabel(f"IN_FREQ[{i}]"), i, 0)
            l.addWidget(e, i, 1); l.addWidget(bs, i, 2); l.addWidget(bg, i, 3)
            self.in_freq_edits.append(e)
        return self._wrap(g)

    def _build_encoder_group(self) -> QWidget:
        g = QGroupBox("Encoder")
        l = QGridLayout(g)
        for i in range(self.counts.get("enc", 0)):
            row = i * 2
            a = QLineEdit("0.0"); r = QLineEdit("0.0"); s = QLineEdit("0.0")
            bsp = QPushButton("Set Pos"); bgp = QPushButton("Get Pos")
            bss = QPushButton("Set Spd"); bgs = QPushButton("Get Spd")
            bsp.clicked.connect(lambda _=False, idx=i: self._set_enc_pos(idx))
            bgp.clicked.connect(lambda _=False, idx=i: self._get_enc_pos(idx))
            bss.clicked.connect(lambda _=False, idx=i: self._set_enc_speed(idx))
            bgs.clicked.connect(lambda _=False, idx=i: self._get_enc_speed(idx))
            l.addWidget(QLabel(f"ENC[{i}] abs/rel"), row, 0)
            l.addWidget(a, row, 1); l.addWidget(r, row, 2); l.addWidget(bsp, row, 3); l.addWidget(bgp, row, 4)
            l.addWidget(QLabel("speed"), row + 1, 0)
            l.addWidget(s, row + 1, 1); l.addWidget(bss, row + 1, 3); l.addWidget(bgs, row + 1, 4)
            self.enc_abs_edits.append(a); self.enc_rel_edits.append(r); self.enc_speed_edits.append(s)
        return self._wrap(g)

    @staticmethod
    def _wrap(widget: QWidget) -> QScrollArea:
        s = QScrollArea()
        s.setWidgetResizable(True)
        s.setWidget(widget)
        return s

    def _refresh_once(self) -> None:
        try:
            parts = self.client.get_all().split()
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

    @staticmethod
    def _set_text_if_not_editing(edit: QLineEdit, value: str) -> None:
        # Keep user input stable while the field is actively being edited.
        if edit.hasFocus():
            return
        if edit.text() != value:
            edit.setText(value)

    def _set_ana(self, i: int) -> None:
        self.client.set_ana(i, _to_float(self.ana_edits[i].text(), 0.0))

    def _get_ana(self, i: int) -> None:
        self.ana_edits[i].setText(f"{self.client.get_ana(i)}")

    def _set_pwm(self, i: int) -> None:
        self.client.set_pwm(i, _to_int(self.pwm_edits[i].text(), 0))

    def _get_pwm(self, i: int) -> None:
        self.pwm_edits[i].setText(f"{self.client.get_pwm(i)}")

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

    def _set_enc_pos(self, i: int) -> None:
        self.client.set_enc_pos(i, _to_float(self.enc_abs_edits[i].text(), 0.0), _to_float(self.enc_rel_edits[i].text(), 0.0))

    def _get_enc_pos(self, i: int) -> None:
        a, r = self.client.get_enc_pos(i)
        self.enc_abs_edits[i].setText(f"{a}")
        self.enc_rel_edits[i].setText(f"{r}")

    def _set_enc_speed(self, i: int) -> None:
        self.client.set_enc_speed(i, _to_float(self.enc_speed_edits[i].text(), 0.0))

    def _get_enc_speed(self, i: int) -> None:
        self.enc_speed_edits[i].setText(f"{self.client.get_enc_speed(i)}")
