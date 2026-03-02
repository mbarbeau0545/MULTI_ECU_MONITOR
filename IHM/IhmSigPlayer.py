#------------------------------------------------------------------------------
#  @file        IhmSigPlayer.py
#  @brief       Signal Player widget for replaying .log files
#------------------------------------------------------------------------------
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QBrush, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QLineEdit, QListWidget, QListWidgetItem, QCheckBox, QComboBox, QGroupBox,
    QFormLayout, QMessageBox
)

import pyqtgraph as pg


@dataclass
class LogPoint:
    t_s: float
    raw: float
    val: float


class _LogParser:
    """
    Supports both formats:
        - legacy:  <t> <signal> <raw> <value>
        - msg-aware: <t> <msg_id> <signal> <raw> <value>
    Where:
        - <t> can be in seconds or milliseconds; we keep it as float then normalize on playback.
        - <msg_id> can be 0x18FF0000, 18FF0000h, 18FF0000, 010, etc.
        - <value> can be numeric or enum string. If enum -> we fallback to raw for plotting.
    """

    _re_split = re.compile(r"\s+")
    _re_hex = re.compile(r"^(?:0x)?([0-9A-Fa-f]+)(?:h)?$")

    @staticmethod
    def _parse_float(token: str) -> Optional[float]:
        val = None
        try:
            val = float(token)
        except Exception:
            val = None
        return val

    @classmethod
    def _norm_msg_id(cls, token: str) -> Optional[str]:
        token = token.strip()
        m = cls._re_hex.match(token)
        if not m:
            return None
        hex_str = m.group(1).upper()
        # normalize width loosely: keep as 0x... uppercase, no leading zeros trimming beyond one char
        msg = f"0x{hex_str.lstrip('0') or '0'}"
        return msg

    @staticmethod
    def _plot_y(raw_s: str, val_s: str) -> Tuple[Optional[float], Optional[float]]:
        raw = _LogParser._parse_float(raw_s)
        val = _LogParser._parse_float(val_s)
        return raw, val

    @classmethod
    def parse_file(cls, path: str) -> Tuple[Dict[str, List[LogPoint]], List[str]]:
        """
        Returns:
            data_by_series: series_name -> list of LogPoint (sorted by t_s)
            series_list: list of series names (stable sorted)
        """
        data_by_series: Dict[str, List[LogPoint]] = {}
        series_list: List[str] = []

        if not os.path.isfile(path):
            return data_by_series, series_list

        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue

                parts = cls._re_split.split(line)
                # Must at least have t + sig + raw + val
                if len(parts) < 4:
                    continue

                t = cls._parse_float(parts[0])
                if t is None:
                    continue

                idx = 1
                msg_id = None

                # Try msg-aware: second token looks like hex id
                if len(parts) >= 5:
                    msg_try = cls._norm_msg_id(parts[1])
                    if msg_try is not None:
                        msg_id = msg_try
                        idx = 2

                # Now expect signal, raw, value (value could be multi-token; we take first token as numeric candidate)
                if idx + 2 >= len(parts):
                    continue

                sig = parts[idx]
                raw_s = parts[idx + 1]
                # value may contain spaces (enum), keep full tail for display, but for plotting we only use first numeric token
                val_s = parts[idx + 2]
                raw_f, val_f = cls._plot_y(raw_s, val_s)

                # if value isn't numeric, fallback to raw for plotting
                if raw_f is None:
                    continue
                if val_f is None:
                    val_f = raw_f

                if msg_id is not None:
                    series = f"{msg_id}:{sig}"
                else:
                    series = sig

                if series not in data_by_series:
                    data_by_series[series] = []
                    series_list.append(series)

                data_by_series[series].append(LogPoint(t_s=float(t), raw=float(raw_f), val=float(val_f)))

        # Sort and normalize time base per series (convert to seconds relative to t0)
        for series, pts in data_by_series.items():
            pts.sort(key=lambda p: p.t_s)
            if pts:
                t0 = pts[0].t_s
                # Heuristic: if times look like milliseconds (big numbers but close), we keep as seconds by /1000 when span is huge
                span = pts[-1].t_s - t0
                # If span > 10_000 it's likely ms or us already, but can't know. We'll treat unit as "same",
                # and only shift to start at 0.
                for i in range(len(pts)):
                    pts[i] = LogPoint(t_s=pts[i].t_s - t0, raw=pts[i].raw, val=pts[i].val)

        series_list = sorted(series_list, key=lambda s: s.lower())
        return data_by_series, series_list


class SignalPlayerWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._log_path: Optional[str] = None
        self._data: Dict[str, List[LogPoint]] = {}
        self._series: List[str] = []

        self._curves: Dict[str, pg.PlotDataItem] = {}
        self._play_pos_s: float = 0.0
        self._playing: bool = False
        self._loop: bool = True
        self._speed: float = 1.0
        self._t_ref: Optional[float] = None
        self._t_end_s: float = 0.0

        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(30)

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # File bar
        file_row = QHBoxLayout()
        self._le_path = QLineEdit()
        self._le_path.setReadOnly(True)
        btn_browse = QPushButton("Open .log")
        btn_browse.clicked.connect(self._on_browse)
        file_row.addWidget(QLabel("Log:"))
        file_row.addWidget(self._le_path, 1)
        file_row.addWidget(btn_browse)
        root.addLayout(file_row)

        # Controls
        ctrl_box = QGroupBox("Playback")
        ctrl = QHBoxLayout(ctrl_box)

        self._btn_play = QPushButton("Play")
        self._btn_play.clicked.connect(self._toggle_play)
        btn_restart = QPushButton("Restart")
        btn_restart.clicked.connect(self._restart)

        self._cb_loop = QCheckBox("Loop")
        self._cb_loop.setChecked(True)
        self._cb_loop.stateChanged.connect(lambda _: self._sync_loop())

        self._cb_speed = QComboBox()
        self._cb_speed.addItems(["0.25x", "0.5x", "1x", "2x", "4x", "8x", "16x", "32x"])
        self._cb_speed.setCurrentText("1x")
        self._cb_speed.currentTextChanged.connect(self._sync_speed)

        ctrl.addWidget(self._btn_play)
        ctrl.addWidget(btn_restart)
        ctrl.addWidget(self._cb_loop)
        ctrl.addWidget(QLabel("Speed:"))
        ctrl.addWidget(self._cb_speed)
        ctrl.addStretch(1)

        root.addWidget(ctrl_box)

        # Selection + plot
        mid = QHBoxLayout()

        left = QVBoxLayout()
        flt_row = QHBoxLayout()
        self._le_filter = QLineEdit()
        self._le_filter.setPlaceholderText("Filter series (name or 0xID:Signal)")
        self._le_filter.textChanged.connect(self._apply_filter)
        flt_row.addWidget(QLabel("Filter:"))
        flt_row.addWidget(self._le_filter)
        left.addLayout(flt_row)

        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_series_toggled)
        left.addWidget(self._list, 1)

        btn_sel_all = QPushButton("Select all")
        btn_sel_none = QPushButton("Select none")
        btn_sel_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_sel_none.clicked.connect(lambda: self._set_all_checked(False))

        sel_row = QHBoxLayout()
        sel_row.addWidget(btn_sel_all)
        sel_row.addWidget(btn_sel_none)
        left.addLayout(sel_row)

        mid.addLayout(left, 0)

        self._plot = pg.PlotWidget(title="Signal Player")
        self._plot.setLabel("bottom", "t", units="s")
        self._plot.setLabel("left", "value")
        self._plot.addLegend()
        mid.addWidget(self._plot, 1)

        root.addLayout(mid, 1)

    # ---------------- events ----------------
    def _on_browse(self) -> None:
        start_dir = os.path.dirname(self._log_path) if self._log_path else os.getcwd()
        path, _ = QFileDialog.getOpenFileName(self, "Select LOG file", start_dir, "Log files (*.log);;All files (*.*)")
        if path:
            self.load_log(path)

    def load_log(self, path: str) -> None:
        self._log_path = path
        self._le_path.setText(path)

        self._data, self._series = _LogParser.parse_file(path)
        self._rebuild_series_list()

        # determine end time over selected series
        self._t_end_s = 0.0
        for pts in self._data.values():
            if pts:
                self._t_end_s = max(self._t_end_s, pts[-1].t_s)

        self._restart()
        self._plot.clear()
        self._plot.addLegend()
        self._curves.clear()

        # auto-select nothing initially (user chooses)
        self._set_all_checked(False)

    def _toggle_play(self) -> None:
        self._playing = not self._playing
        self._t_ref = None
        self._btn_play.setText("Pause" if self._playing else "Play")

    def _restart(self) -> None:
        self._play_pos_s = 0.0
        self._t_ref = None
        self._redraw_all()

    def _sync_loop(self) -> None:
        self._loop = self._cb_loop.isChecked()

    def _sync_speed(self, text: str) -> None:
        # text like "2x"
        sp = 1.0
        try:
            sp = float(text.replace("x", ""))
        except Exception:
            sp = 1.0
        self._speed = sp

    def _apply_filter(self) -> None:
        q = self._le_filter.text().strip().lower()
        for i in range(self._list.count()):
            it = self._list.item(i)
            name = (it.text() or "").lower()
            it.setHidden(bool(q) and (q not in name))

    def _rebuild_series_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for s in self._series:
            it = QListWidgetItem(s)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self._list.addItem(it)
        self._list.blockSignals(False)
        self._apply_filter()

    def _set_all_checked(self, checked: bool) -> None:
        self._list.blockSignals(True)
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self._list.count()):
            it = self._list.item(i)
            it.setCheckState(state)
        self._list.blockSignals(False)
        self._on_selection_changed()

    def _on_series_toggled(self, _: QListWidgetItem) -> None:
        self._on_selection_changed()

    def _on_selection_changed(self) -> None:
        # rebuild curves to match checked items
        checked = []
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.checkState() == Qt.Checked and not it.isHidden():
                checked.append(it.text())

        # Remove curves not selected
        for name in list(self._curves.keys()):
            if name not in checked:
                self._plot.removeItem(self._curves[name])
                del self._curves[name]

        # Add missing curves
        for name in checked:
            if name in self._curves:
                continue
            curve = self._plot.plot([], [], name=name, pen=pg.intColor(len(self._curves)))
            self._curves[name] = curve

        self._redraw_all()

    def _redraw_all(self) -> None:
        # display points up to play position
        for name, curve in self._curves.items():
            pts = self._data.get(name, [])
            if not pts:
                curve.setData([], [])
                continue

            xs = []
            ys = []
            for p in pts:
                if p.t_s <= self._play_pos_s:
                    xs.append(p.t_s)
                    ys.append(p.val)
                else:
                    break
            curve.setData(xs, ys)

    def _on_tick(self) -> None:
        if not self._playing:
            return
        if not self._curves:
            return
        if self._t_end_s <= 0.0:
            return

        now = time.perf_counter()
        if self._t_ref is None:
            self._t_ref = now
            return

        dt = (now - self._t_ref) * self._speed
        self._t_ref = now
        self._play_pos_s += dt

        if self._play_pos_s >= self._t_end_s:
            if self._loop:
                self._play_pos_s = 0.0
            else:
                self._play_pos_s = self._t_end_s
                self._playing = False
                self._btn_play.setText("Play")

        self._redraw_all()
