"""
#  @file        main.py
#  @brief       Template_BriefDescription.
#  @details     TemplateDetailsDescription.\n
#
#  @author      mba
#  @date        jj/mm/yyyy
#  @version     1.0
"""
#------------------------------------------------------------------------------
#                                       IMPORT
#------------------------------------------------------------------------------
import sys, json
import math
import os
from collections import deque
import sys, time
import os
from PyQt5.QtWidgets import (
QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QPushButton,
QVBoxLayout, QWidget, QTabWidget, QHBoxLayout, QLabel, QLineEdit, QComboBox,
QScrollArea, QFrame, QAction, QMenu, QToolBar, QHeaderView, QSplitter, QGroupBox,
QFormLayout,QFileDialog, QTreeWidget,QTreeWidgetItem
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QBrush, QFontMetrics

import pyqtgraph as pg

from IHM.IhmSigPlayer import SignalPlayerWidget
from Frame.frameMngmt import FrameMngmt
from Signal.ActSnsMngmt import ActInfo, SnsInfo
from typing import List, Dict
#------------------------------------------------------------------------------
#                                       CONSTANT
#------------------------------------------------------------------------------
# application constants
REFRESH_IMH_SECONDS = 50  # ms
PLOT_MAX_POINT = 2000
GRAPH_CONFIG_FILENAME = "graph_config.json"
ACT_CTRL_FILENAME = "act_controls.json"
# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
#------------------------------------------------------------------------------
#                                       CLASS
#------------------------------------------------------------------------------


class SignalViewer(QMainWindow):
    def __init__(self, f_prj_cfg: str):
        super().__init__()

        if not os.path.isfile(f_prj_cfg):
            raise FileNotFoundError(f'Signal Config file doest not exits {f_prj_cfg}')
        
        self.prj_cfg = f_prj_cfg
        with open(self.prj_cfg, "r") as file:
            self.prj_cfg_data = json.load(file)

        try:
            excel_path = self.prj_cfg_data["excel_cfg"]
        except (KeyError, TypeError, AttributeError) as e:
            raise Exception(f'An error occured while extracting config project -> {e}')
        
        # --- app paths ---
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.graph_cfg_path = os.path.join(self.app_dir, GRAPH_CONFIG_FILENAME)
        self.act_ctrl_path = os.path.join(self.app_dir, ACT_CTRL_FILENAME)

        # init frame instance
        self.frame_isct = FrameMngmt(self.prj_cfg)
        self.is_ecu_connected = False
        self.last_try_con = 0

        self.setWindowTitle("Signal Viewer")
        self.resize(1200, 800)

        self.signals_name = self.frame_isct.get_signal_list()

        # utilisation de deque pour éviter l'écrasement
        self.signals_values = {
            signal_name: deque(maxlen=PLOT_MAX_POINT)
            for signal_name in self.signals_name
        }
        self.previous_values = {signal_name: -1 for signal_name in self.signals_name}

        

        # msg-specific buffers (avoid collisions when same signal name exists in different CAN IDs)
        self.msg_signals_values = {}   # key: "0xID:Signal" -> deque([raw, calc, ts])
        self.msg_previous_values = {}  # key: (msg_id:int, signal_name:str) -> last raw string
        self.frame_isct.get_symbol_list()

        

        # ========================
        # UI Setup
        # ========================
        self._create_toolbar()

        # Création du QTabWidget
        self.tab_widget = QTabWidget()

        # --- Messages tab (PCAN-Symbol style) ---
        self._init_messages_tab()

        # --- Message Sender tab ---
        self.msg_sender_widget = QWidget()
        self.msg_sender_layout = QVBoxLayout(self.msg_sender_widget)
        btn_add_msg = QPushButton("Add message")
        btn_add_msg.clicked.connect(self.__add_message_row)
        self.msg_sender_layout.addWidget(btn_add_msg)
        self.msg_scroll = QScrollArea()
        self.msg_scroll.setWidgetResizable(True)
        self.msg_container = QWidget()
        self.msg_rows_container = QVBoxLayout(self.msg_container)
        self.msg_container.setLayout(self.msg_rows_container)
        self.msg_scroll.setWidget(self.msg_container)
        self.msg_sender_layout.addWidget(self.msg_scroll)
        self.tab_widget.addTab(self.msg_sender_widget, "Message Sender")

        # --- Sensors / Actuators ---
        self.sensors = SnsInfo(excel_path)
        self.actuator = ActInfo(excel_path)
        self.act_control_values = self._load_act_controls()

        self._init_sensors_tab()       # <-- crée et remplit l'onglet Sensors
        self._init_actuators_tab()     # <-- crée et remplit l'onglet Actuators
        # load persisted actuator controls
        # === Ajout du tab_widget comme contenu principal ===
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tab_widget)
        self.setCentralWidget(container)

        # ========================
        # Timers de mise à jour
        # ========================
        self.__connect_ecu()
        self.timer = QTimer()
        self.timer.timeout.connect(self.__refresh_table)
        self.timer.start(REFRESH_IMH_SECONDS)  # ms

        # timer de garde (évite freeze de l’UI si pas de signal)
        self._timer_interrupt = QTimer()
        self._timer_interrupt.timeout.connect(lambda: None)
        self._timer_interrupt.start(REFRESH_IMH_SECONDS)

        # try to restore saved graphs
        self._load_graphs_state()


    #--------------------------
    # _mk_sig_key
    #--------------------------
    def _mk_sig_key(self, f_msg_id: int, f_sig_name: str) -> str:
        """Build a unique signal identifier for a given CAN msg id."""
        try:
            mid = int(f_msg_id)
        except Exception:
            mid = 0
        return f"0x{mid:X}:{str(f_sig_name)}"

    #--------------------------
    # _get_plot_deque
    #--------------------------
    def _get_plot_deque(self, f_sig_id: str):
        """Return the deque used to plot a signal (msg-specific if available)."""
        if hasattr(self, "msg_signals_values") and f_sig_id in self.msg_signals_values:
            return self.msg_signals_values[f_sig_id]
        return self.signals_values.get(f_sig_id)


    # ------------------------- toolbar -------------------------
    def _create_toolbar(self):
        toolbar = self.addToolBar("Main Toolbar")

        # --- Refresh Connection Button ---
        self.btn_refresh = QPushButton("Refresh Connection")
        self.btn_refresh.clicked.connect(self.__connect_ecu)
        toolbar.addWidget(self.btn_refresh)

        # --- Load Signal CFG ---
        btn_load_signal = QPushButton("Load Signal CFG")
        btn_load_signal.clicked.connect(self.__load_signal_cfg)
        toolbar.addWidget(btn_load_signal)

        # --- Load Excel CFG ---
        btn_load_excel = QPushButton("Load Excel CFG")
        btn_load_excel.clicked.connect(self.__load_excel_cfg)
        toolbar.addWidget(btn_load_excel)

        # --- Signal Player ---
        btn_sig_player = QPushButton("SIGNAL PLAYER")
        btn_sig_player.clicked.connect(self.__open_signal_player)
        toolbar.addWidget(btn_sig_player)

    #--------------------------
    # __open_signal_player
    #--------------------------
    def __open_signal_player(self) -> None:
        """
        Open (or focus) the Signal Player tab.
        It replays .log files generated by FrameMngmt (_cyclic_can_frame/_cyclic_serial_frame).
        """
        tab_name = "Signal Player"
        found_idx = -1

        for i in range(self.tab_widget.count()):
            if self.tab_widget.tabText(i) == tab_name:
                found_idx = i
                break

        if found_idx >= 0:
            self.tab_widget.setCurrentIndex(found_idx)
        else:
            w = QWidget()
            lay = QVBoxLayout(w)
            player = SignalPlayerWidget(w)
            lay.addWidget(player)
            self.tab_widget.addTab(w, tab_name)
            self.tab_widget.setCurrentWidget(w)

    #--------------------------
    # kill_all_thread
    #--------------------------
    def kill_all_thread(self):
        """Kill all thread currently on going """
        self.frame_isct.unperform_cyclic()

    #--------------------------
    # __connect_ecu
    #--------------------------
    def __connect_ecu(self):
        self.last_try_con = time.time()
        try:
            self.frame_isct.perform_cyclic()
            self.is_ecu_connected = True
            print("[INFO] : Connection succeeded, ECU connected")
        except Exception as e:
            print(f"[INFO] : Connection Failed -> {e}")
            self.is_ecu_connected = False

        self.__update_refresh_btn_color()

    #--------------------------
    # __refresh_table
    #--------------------------

    def __refresh_table(self):
        curr_time = time.time()
        if not self.is_ecu_connected and (curr_time - self.last_try_con) > 5:
            self.__connect_ecu()
            return

        # Iterate symbols/messages to keep signal context (msg_id + signal_name)
        for sym_name, sym_info in self.frame_isct.symbol.items():
            msg_id = sym_info.get('msg_id', None)
            if msg_id is None:
                continue

            # Only mux index '0' is used in this UI refresh for now
            sigs = sym_info.get('signals', {}).get('0', {})
            if not isinstance(sigs, dict):
                continue

            for signal_name in sigs.keys():
                # Pull new samples for this (msg_id, signal)
                try:
                    sig_val = self.frame_isct.get_msg_signal_value(str(msg_id), str(signal_name))
                except Exception:
                    continue

                if sig_val == [[]] or sig_val == []:
                    continue

                # Store for plots (msg-specific)
                sig_id = self._mk_sig_key(msg_id, signal_name)
                if sig_id not in self.msg_signals_values:
                    self.msg_signals_values[sig_id] = deque(maxlen=PLOT_MAX_POINT)

                for sig_info in sig_val:
                    if sig_info:
                        self.msg_signals_values[sig_id].append(sig_info)

                if not (sig_val and sig_val[-1]):
                    continue

                raw_txt = "" if sig_val[-1][0] is None else str(sig_val[-1][0])
                calc_txt = "" if sig_val[-1][1] is None else str(sig_val[-1][1])

                msg_key = (int(msg_id), str(signal_name))
                prev_raw = self.msg_previous_values.get(msg_key)

                # Update message tree item
                if hasattr(self, '_sig_items') and msg_key in getattr(self, '_sig_items', {}):
                    child: QTreeWidgetItem = self._sig_items[msg_key]
                    child.setData(2, Qt.DisplayRole, raw_txt)
                    child.setData(1, Qt.DisplayRole, calc_txt)

                    # Highlight on change
                    if prev_raw is not None and prev_raw != raw_txt:
                        brush = QBrush(QColor("yellow"))
                    else:
                        brush = QBrush(QColor("white"))
                    child.setBackground(1, brush)
                    child.setBackground(2, brush)

                self.msg_previous_values[msg_key] = raw_txt

                # Update sensors widget values (unique names)
                if str(signal_name).upper().startswith("SNS"):
                    self._refresh_sensors_values(str(signal_name), calc_txt)

                # Update act widget values (unique names)
                if str(signal_name).upper().startswith("ACT"):
                    self._refresh_actuators_get_values(str(signal_name), calc_txt)

    def __open_graph_tab(self, signal_name, saved_signals: List[str] = None):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Boutons
        btn_toggle = QPushButton("Stop")
        btn_close = QPushButton("Close Tab")
        layout.addWidget(btn_toggle)
        layout.addWidget(btn_close)

        btn_close.clicked.connect(lambda _, w=widget: self.__close_tab(w))
        btn_toggle.clicked.connect(lambda _, w=widget, b=btn_toggle: self.__toggle_pause(w, b))

        # Plot
        plot_widget = pg.PlotWidget(title="Signals")
        plot_widget.setLabel('bottom', 'Temps', units='s')
        plot_widget.setLabel('left', 'Valeur')
        plot_widget.addLegend()
        plot_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        plot_widget.customContextMenuRequested.connect(
            lambda pos, w=widget: self.__show_graph_context_menu(w, pos)
        )
        layout.addWidget(plot_widget)

        # Ajout de l'onglet
        self.tab_widget.addTab(widget, signal_name)
        self.tab_widget.setCurrentWidget(widget)

        # Stockage
        widget._curves = {}
        widget._plot_widget = plot_widget
        widget._t0 = None
        widget._paused = False

        # Ajouter le premier signal (or use saved list)
        if saved_signals:
            for s in saved_signals:
                self.__add_signal_to_tab(widget, s)
        else:
            self.__add_signal_to_tab(widget, signal_name)

        # Fonction update
        def update_plot():
            if widget._paused:
                return

            # init t0 commun
            if widget._t0 is None:
                min_t0 = None
                for sig_name in widget._curves.keys():
                    dq = self._get_plot_deque(sig_name)
                    if dq:
                        t0_candidate = dq[0][2]
                        if min_t0 is None or t0_candidate < min_t0:
                            min_t0 = t0_candidate
                widget._t0 = min_t0
                if widget._t0 is None:
                    return

            # mise à jour par signal
            for sig_name, sig_data in list(widget._curves.items()):
                dq = self._get_plot_deque(sig_name)
                if dq is None:
                    continue
                while dq:
                    raw, calc, ts = dq[0]
                    if ts < widget._t0:
                        dq.popleft()
                        continue

                    try:
                        t_sec = float(ts - widget._t0) / 1e9
                    except (TypeError, ValueError):
                        dq.popleft()
                        continue

                    try:
                        y_val = float(calc)
                    except (TypeError, ValueError):
                        # Non-numeric values (enum strings, etc.) cannot be plotted.
                        dq.popleft()
                        continue

                    if not (math.isfinite(t_sec) and math.isfinite(y_val)):
                        dq.popleft()
                        continue

                    if not sig_data["times"] or t_sec > sig_data["times"][-1]:
                        sig_data["times"].append(t_sec)
                        sig_data["values"].append(y_val)
                    dq.popleft()

                # découpe et affichage
                if len(sig_data["times"]) > PLOT_MAX_POINT:
                    sig_data["times"] = sig_data["times"][-PLOT_MAX_POINT:]
                    sig_data["values"] = sig_data["values"][-PLOT_MAX_POINT:]

                if len(sig_data["times"]) > 1:
                    # Safety net for previously buffered invalid samples.
                    clean_t = []
                    clean_y = []
                    for t_val, y_val in zip(sig_data["times"], sig_data["values"]):
                        try:
                            t_f = float(t_val)
                            y_f = float(y_val)
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(t_f) and math.isfinite(y_f):
                            clean_t.append(t_f)
                            clean_y.append(y_f)

                    sig_data["times"] = clean_t[-PLOT_MAX_POINT:]
                    sig_data["values"] = clean_y[-PLOT_MAX_POINT:]

                    if len(sig_data["times"]) > 1:
                        sig_data["curve"].setData(sig_data["times"], sig_data["values"])

        # Timer Qt
        timer = QTimer(widget)
        timer.timeout.connect(update_plot)
        timer.start(REFRESH_IMH_SECONDS)
        widget._timer = timer

        # attach tab metadata for persistence
        widget._saved_tab_title = signal_name

        # when tab is closed via GUI we must save state
        return widget
    # ------------------------------
    # SIGNALS TAB
    # ------------------------------
    
    def _format_msg_direction(self, direction):
        """Format msg_direction which can be a string or a dict (multi-ECU)."""
        if isinstance(direction, dict):
            parts = []
            for ecu, d in direction.items():
                parts.append(f"{ecu}:{d}")
            return ", ".join(parts) if parts else ""
        if isinstance(direction, str):
            return direction
        return ""

    def _init_messages_tab(self):
        """Initialise l'onglet Messages (vue type PCAN-Symbol)."""
        self.msgs_widget = QWidget()
        self.msgs_layout = QVBoxLayout(self.msgs_widget)

        # --- Search / filter bar ---
        bar = QHBoxLayout()
        lbl = QLabel("Search:")
        self.msg_search_le = QLineEdit()
        self.msg_search_le.setPlaceholderText("Message name or ID (e.g. ABS, 18FF9, 0x18FF9998)")
        self.msg_search_le.textChanged.connect(self.__apply_msg_filter)
        bar.addWidget(lbl)
        bar.addWidget(self.msg_search_le)
        self.msgs_layout.addLayout(bar)

        # --- Tree ---
        self.msg_tree = QTreeWidget()
        self.msg_tree.setColumnCount(4)
        self.msg_tree.setHeaderLabels(["Name", "ID / Raw", "Dir / Value", "Graph"])
        self.msg_tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.msg_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.msg_tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.msg_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.msg_tree.setRootIsDecorated(True)
        self.msg_tree.setAlternatingRowColors(True)

        self.msgs_layout.addWidget(self.msg_tree)
        self.tab_widget.addTab(self.msgs_widget, "Messages")

        self._build_messages_tree()

    def _build_messages_tree(self):
        """Build the tree from symbols. Creates mapping signal->item for fast refresh."""
        self.msg_tree.clear()
        self._msg_items = {}      # sym_name -> QTreeWidgetItem
        self._sig_items = {}      # (msg_id:int, signal_name:str) -> QTreeWidgetItem
        self._plot_signal_ids = []  # list of unique signal identifiers for plotting

        sym_list = []
        try:
            sym_list = self.frame_isct.get_symbol_list()
        except Exception:
            sym_list = []

        # Stable ordering for human scanning
        sym_list = sorted(sym_list, key=lambda s: str(s).lower())

        for sym_name in sym_list:
            sym = getattr(self.frame_isct, 'symbol', {}).get(sym_name, {})
            msg_id = sym.get('msg_id', None)
            dir_s = self._format_msg_direction(sym.get('msg_direction', ''))
            id_s = ""
            if msg_id is not None:
                try:
                    id_s = f"0x{int(msg_id):X}"
                except Exception:
                    id_s = str(msg_id)

            top = QTreeWidgetItem([str(sym_name), id_s, dir_s, ""])
            top.setFirstColumnSpanned(False)
            self.msg_tree.addTopLevelItem(top)
            self._msg_items[sym_name] = top

            # signals can be muxed: sym['signals'] is a dict indexed by mux value as string.
            sigs_root = sym.get('signals', {})
            if isinstance(sigs_root, dict):
                mux_keys = sorted(sigs_root.keys(), key=lambda k: str(k))
                for mux_k in mux_keys:
                    sigs = sigs_root.get(mux_k, {})
                    if not isinstance(sigs, dict):
                        continue
                    for sig_name in sorted(sigs.keys(), key=lambda s: str(s).lower()):
                        child = QTreeWidgetItem([str(sig_name), "", "", ""])
                        top.addChild(child)

                        btn = QPushButton("Graph")
                        sig_id = self._mk_sig_key(msg_id if msg_id is not None else 0, str(sig_name))
                        self._plot_signal_ids.append(sig_id)
                        btn.clicked.connect(lambda _, s=sig_id: self.__open_graph_tab(s))
                        self.msg_tree.setItemWidget(child, 3, btn)

                        msg_key = (int(msg_id) if msg_id is not None else 0, str(sig_name))
                        self._sig_items[msg_key] = child

            top.setExpanded(False)

        self.__apply_msg_filter()

    def __apply_msg_filter(self):
        """Filter top-level messages by name or ID."""
        if not hasattr(self, 'msg_tree'):
            return

        q = self.msg_search_le.text().strip().lower() if hasattr(self, 'msg_search_le') else ""
        q_norm = q.replace("0x", "").replace(" ", "")
        for i in range(self.msg_tree.topLevelItemCount()):
            item = self.msg_tree.topLevelItem(i)
            name = (item.text(0) or "").lower()
            mid = (item.text(1) or "").lower()
            mid_norm = mid.replace("0x", "").replace(" ", "")
            match = True
            if q_norm:
                match = (q_norm in name) or (q_norm in mid_norm) or (q in mid)
            item.setHidden(not match)

    def _init_signals_tab(self):
        """Initialise l'onglet Signals"""
        self.signals_widget = QWidget()
        self.signals_layout = QVBoxLayout(self.signals_widget)

        self.table = QTableWidget(len(self.signals_name), 4)
        self.table.setHorizontalHeaderLabels(["Signal", "Raw Value", "Value", "Graph"])
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(2, 150)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.signals_layout.addWidget(self.table)
        self.tab_widget.addTab(self.signals_widget, "Signals")

        # Remplissage initial
        for row, signal_name in enumerate(self.signals_name):
            self.table.setItem(row, 0, QTableWidgetItem(signal_name))
            btn = QPushButton("Graph")
            btn.clicked.connect(lambda _, s=signal_name: self.__open_graph_tab(s))
            self.table.setCellWidget(row, 3, btn)


    # ------------------------------
    # SENSORS TAB
    # ------------------------------
    def _init_sensors_tab(self):
        """Initialise l'onglet Sensors"""
        self.sensors_widget = QWidget()
        layout = QVBoxLayout(self.sensors_widget)

        self.sensors_table = QTableWidget()
        self.sensors_table.setColumnCount(3)
        self.sensors_table.setHorizontalHeaderLabels(["Sensor", "Unit", "Value"])
        self.sensors_table.horizontalHeader().setStretchLastSection(True)

        layout.addWidget(self.sensors_table)
        self.tab_widget.addTab(self.sensors_widget, "Sensors")

        # Remplissage initial
        keys = list(self.sensors.info.keys())
        self.sensors_table.setRowCount(len(keys))
        for row, key in enumerate(keys):
            self.sensors_table.setItem(row, 0, QTableWidgetItem(key))
            self.sensors_table.setItem(row, 1, QTableWidgetItem(self.sensors.info[key]["unity"]))

            # Valeur actuelle
            sig_name = self.sensors.info[key]["signal"]
            val = self.frame_isct.get_signal_value(sig_name)
            display_val = str(val[-1][1]) if val and val[-1] else "N/A"
            self.sensors_table.setItem(row, 2, QTableWidgetItem(display_val))


    # ------------------------------
    # ACTUATORS TAB
    # ------------------------------
    def _init_actuators_tab(self):
        """Initialise l'onglet Actuators"""
        self.actuators_widget = QWidget()
        layout = QVBoxLayout(self.actuators_widget)

        self.actuators_tab_widget = QTabWidget()
        layout.addWidget(self.actuators_tab_widget)

        # ---- Interface tab ----
        interface_widget = QWidget()
        interface_layout = QVBoxLayout(interface_widget)
        self.actuators_interface_table = QTableWidget()
        self.actuators_interface_table.setColumnCount(4)
        self.actuators_interface_table.setHorizontalHeaderLabels(
            ["Actuator", "Set Value", "Get Value", "Control"]
        )
        self.actuators_interface_table.horizontalHeader().setStretchLastSection(True)
        interface_layout.addWidget(self.actuators_interface_table)
        self.actuators_tab_widget.addTab(interface_widget, "Interface")

        # Remplissage
        keys = list(self.actuator.info.keys())
        self.actuators_interface_table.setRowCount(len(keys))
        for row, key in enumerate(keys):
            info = self.actuator.info[key]
            self.actuators_interface_table.setItem(row, 0, QTableWidgetItem(key))
            # Valeurs set et get actuelles
            val_set = self.frame_isct.get_signal_value(info["set_sig"])
            val_get = self.frame_isct.get_signal_value(info["get_sig"])
            self.actuators_interface_table.setItem(row, 1, QTableWidgetItem(str(val_set[-1][1]) if val_set and val_set[-1] else "N/A"))
            self.actuators_interface_table.setItem(row, 2, QTableWidgetItem(str(val_get[-1][1]) if val_get and val_get[-1] else "N/A"))
            # Controle
            edit_ctrl = QLineEdit()
            edit_ctrl.setObjectName(key)
            self.actuators_interface_table.setCellWidget(row, 3, edit_ctrl)
            for actitf_dict in self.act_control_values.values():
                if key in actitf_dict.keys():
                    edit_ctrl.setText(str(actitf_dict[key]))
            edit_ctrl.editingFinished.connect(lambda k=key, e=edit_ctrl: self._store_act_control_value(k, e.text()))

        # ---- Device tab ----
        device_widget = QWidget()
        device_layout = QVBoxLayout(device_widget)
        self.actuators_device_table = QTableWidget()
        self.actuators_device_table.setColumnCount(3)
        self.actuators_device_table.setHorizontalHeaderLabels(["Device", "Start", "Stop"])
        self.actuators_device_table.horizontalHeader().setStretchLastSection(True)
        device_layout.addWidget(self.actuators_device_table)
        self.actuators_tab_widget.addTab(device_widget, "Device")

        # Remplissage
        dvc_list = self.actuator.dvc_list
        self.actuators_device_table.setRowCount(len(dvc_list))
        for row, dvc_name in enumerate(dvc_list):
            self.actuators_device_table.setItem(row, 0, QTableWidgetItem(dvc_name))

            btn_start = QPushButton("Start")
            btn_start.clicked.connect(lambda _, d=dvc_name: self.send_act_dvc_values(d))
            self.actuators_device_table.setCellWidget(row, 1, btn_start)

            btn_stop = QPushButton("Stop")
            btn_stop.clicked.connect(lambda _, d=dvc_name: self.stop_act_dvc(d))
            self.actuators_device_table.setCellWidget(row, 2, btn_stop)

        self.tab_widget.addTab(self.actuators_widget, "Actuators")
        
    def __add_signal_to_tab(self, widget, signal_name: str):
        if signal_name in widget._curves:
            return  # déjà présent
        color = pg.intColor(len(widget._curves))  # couleur auto
        curve = widget._plot_widget.plot([], [], pen=color, name=signal_name)
        widget._curves[signal_name] = {
            "times": [],
            "values": [],
            "curve": curve
        }

    def __remove_signal_from_tab(self, widget, signal_name: str):
        if signal_name in widget._curves:
            widget._plot_widget.removeItem(widget._curves[signal_name]["curve"])
            del widget._curves[signal_name]

    def __show_graph_context_menu(self, widget, pos):
        menu = QMenu(widget)

        # Signaux déjà affichés
        if widget._curves:
            submenu_remove = menu.addMenu("Supprimer un signal")
            for sig_name in list(widget._curves.keys()):
                action = QAction(sig_name, self)
                action.triggered.connect(
                    lambda _, s=sig_name: self.__remove_signal_from_tab(widget, s)
                )
                submenu_remove.addAction(action)

        # Signaux disponibles à ajouter
        src = getattr(self, '_plot_signal_ids', self.signals_name)
        available = [s for s in src if s not in widget._curves]
        if available:
            submenu_add = menu.addMenu("Ajouter un signal")
            for sig_name in available:
                action = QAction(sig_name, self)
                action.triggered.connect(
                    lambda _, s=sig_name: self.__add_signal_to_tab(widget, s)
                )
                submenu_add.addAction(action)

        # Afficher le menu au bon endroit
        menu.exec_(widget._plot_widget.mapToGlobal(pos))

    def __close_tab(self, f_widget):
        index = self.tab_widget.indexOf(f_widget)
        if index != -1:
            tab_title = self.tab_widget.tabText(index)

            self.tab_widget.removeTab(index)

            if hasattr(f_widget, '_timer'):
                f_widget._timer.stop()

            f_widget.deleteLater()

            # mettre à jour le JSON
            self._remove_tab_from_config(tab_title)

    def __toggle_pause(self, f_widget, f_btn_toggle):
        f_widget._paused = not f_widget._paused
        f_btn_toggle.setText("Start" if f_widget._paused else "Stop")

    #--------------------------
    # Message sender UI
    #--------------------------
    def __add_message_row(self):
        """Ajoute une ligne pour configurer un message"""
        row_widget = QFrame()
        row_widget.setFrameShape(QFrame.StyledPanel)
        row_widget.setFrameShadow(QFrame.Raised)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(10, 5, 10, 5)
        row_layout.setSpacing(15)

        combo = QComboBox()
        combo.addItems(self.frame_isct.get_symbol_list())
        combo.setMinimumWidth(180)
        row_layout.addWidget(combo)

        sig_table = QTableWidget()
        sig_table.setColumnCount(2)
        sig_table.setHorizontalHeaderLabels(["Signal (bits)", "Value"])
        sig_table.horizontalHeader().setStretchLastSection(True)
        sig_table.setAlternatingRowColors(True)
        sig_table.setStyleSheet("""
            QTableWidget::item { padding: 4px; }
            QHeaderView::section {
                background-color: #e0e0e0;
                font-weight: bold;
                padding: 4px;
            }
        """)
        row_layout.addWidget(sig_table, 1)

        if combo.count() > 0:
            self.__populate_signals(sig_table, combo.currentText())

        combo.currentTextChanged.connect(
            lambda sym: self.__populate_signals(sig_table, sym)
        )

        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)

        cyc_layout = QHBoxLayout()
        cyc_layout.addWidget(QLabel("Cyclic (ms):"))
        cyclic_edit = QLineEdit("0")
        cyclic_edit.setFixedWidth(60)
        cyc_layout.addWidget(cyclic_edit)
        right_layout.addLayout(cyc_layout)

        btn_send = QPushButton("Send")
        btn_send.setFixedWidth(70)
        right_layout.addWidget(btn_send)

        btn_send.clicked.connect(
            lambda _, cb=combo, st=sig_table, ce=cyclic_edit, rw=row_widget:
                self.__send_message(cb.currentText(), st, ce.text(), rw)
        )

        btn_delete = QPushButton("Delete")
        btn_delete.setFixedWidth(70)
        btn_delete.setStyleSheet("background-color: #f28b82;")
        right_layout.addWidget(btn_delete)

        btn_delete.clicked.connect(lambda _, rw=row_widget: self.__delete_message_row(rw))

        right_layout.addStretch()
        row_layout.addLayout(right_layout)

        self.msg_rows_container.addWidget(row_widget)

    def __populate_signals(self, table: QTableWidget, sym_name: str):
        table.clearContents()
        table.setRowCount(0)

        signals = self.frame_isct.get_signal_info_from_symbol(sym_name)
        if not signals:
            return

        row_height = 30
        max_visible_rows = 5

        table.setRowCount(len(signals))
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Signal (bits), (factor), (offset)", "Value"])
        table.horizontalHeader().setStretchLastSection(True)

        font = table.font()
        metrics = QFontMetrics(font)
        max_width = 0

        for row, (sig_name, info_sig) in enumerate(signals.items()):
            text = f"{sig_name} ({info_sig['length']}b, {info_sig['factor']}*, {info_sig['offset']}+)"
            item = QTableWidgetItem(text)
            item.setFlags(Qt.ItemIsEnabled)
            table.setItem(row, 0, item)

            edit = QLineEdit()
            edit.setObjectName(sig_name)
            table.setCellWidget(row, 1, edit)

            table.setRowHeight(row, row_height)

            width = metrics.horizontalAdvance(text) + 20
            if width > max_width:
                max_width = width

        table.setColumnWidth(0, max_width)

        header_height = table.horizontalHeader().height()
        visible_rows = min(len(signals), max_visible_rows)
        table.setFixedHeight(header_height + row_height * visible_rows)

        table.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if len(signals) <= max_visible_rows else Qt.ScrollBarAsNeeded
        )

    def __delete_message_row(self, row_widget: QWidget):
        if hasattr(row_widget, "_timer") and row_widget._timer is not None:
            row_widget._timer.stop()
            row_widget._timer.deleteLater()

        self.msg_rows_container.removeWidget(row_widget)
        row_widget.deleteLater()

    def __send_message(self, sym_name: str, table: QTableWidget, cyclic_val: str, row_widget: QWidget):
        signals = {}
        if table and isinstance(table, QTableWidget):
            for row in range(table.rowCount()):
                sig_item = table.item(row, 0)
                sig_name = sig_item.text().split(" ")[0] if sig_item else ""
                edit = table.cellWidget(row, 1)
                try:
                    signals[sig_name] = int(edit.text())
                except (ValueError, AttributeError):
                    signals[sig_name] = 0

        cyclic_val = int(cyclic_val) if str(cyclic_val).isdigit() else 0
        if cyclic_val > 0:
            print(f"[Cyclic] Send {sym_name} every {cyclic_val}ms with {signals}")
            timer = QTimer(row_widget)
            timer.timeout.connect(lambda: self.frame_isct.send_signal_msg(signals, sym_name))
            timer.start(cyclic_val)
            row_widget._timer = timer
        else:
            print(f"[Once] Send {sym_name} with {signals}")
            self.frame_isct.send_signal_msg(signals, sym_name)

    # ----------------------- Sensors tab -----------------------
    def _build_sensors_tab(self):
        # build UI for sensors and add to main tabs
        w = QWidget()
        layout = QVBoxLayout(w)

        self.sensors_table = QTableWidget()
        keys = list(self.sensors.info.keys())
        self.sensors_table.setColumnCount(3)
        self.sensors_table.setHorizontalHeaderLabels(["Sensor", "Unit", "Value"])
        self.sensors_table.setRowCount(len(keys))
        for r, key in enumerate(keys):
            self.sensors_table.setItem(r, 0, QTableWidgetItem(key))
            unit = self.sensors.info[key].get("unity", "")
            self.sensors_table.setItem(r, 1, QTableWidgetItem(str(unit)))
            self.sensors_table.setItem(r, 2, QTableWidgetItem(""))
        layout.addWidget(self.sensors_table)

        self.tab_widget.addTab(w, "Sensors")

    def _refresh_sensors_values(self, f_sig_name, f_sig_val):
        # update values from frame_isct
        for r, key in enumerate(list(self.sensors.info.keys())):
            sig_name = self.sensors.info[key].get("signal")
            if f_sig_name == sig_name:
                self.sensors_table.setItem(r, 2, QTableWidgetItem(f_sig_val))

    def _refresh_actuators_get_values(self, f_sig_name, f_sig_val):
        # update the get_sig column with live values
        for r, key in enumerate(list(self.actuator.info.keys())):
            get_sig = self.actuator.info[key].get("get_sig")
            if get_sig == f_sig_name:
                self.actuators_interface_table.setItem(r, 2, QTableWidgetItem(f_sig_val))
            else:
                set_sig = self.actuator.info[key].get("set_sig")
                if set_sig == f_sig_name:
                    self.actuators_interface_table.setItem(r, 1, QTableWidgetItem(f_sig_val))
    

    def _store_act_control_value(self, actuator_itf_key: str, text_val: str):
        s = text_val.strip()
        if not s:
            raise ValueError("Valeur vide")

        # 1) Entier signé décimal : -123, +42, 0
        try:
            val = int(s, 10)
        except ValueError:
            # 2) Hexadécimal : accepte "0x1A", "1A", "-0x1A", "-1A"
            neg = False
            t = s

            if t[0] in "+-":
                neg = (t[0] == "-")
                t = t[1:].strip()

            if t.lower().startswith("0x"):
                t = t[2:]

            if not t:
                raise ValueError(f"Valeur invalide (hex vide): {text_val!r}")

            try:
                val = int(t, 16)
            except ValueError as e:
                raise ValueError(
                    f"Valeur invalide: attendu un entier signé décimal ou un hexadécimal, reçu {text_val!r}"
                ) from e

            if neg:
                val = -val
                
        # find the device 
        for key in self.act_control_values.keys():
            if key in str(actuator_itf_key):
                self.act_control_values[key][actuator_itf_key] = val

        print(f"For device {key} interface {actuator_itf_key}, save {val}")


    # ----------------------- actuator device placeholders -----------------------
    def send_act_dvc_values(self, device_name: str):
        """
        Placeholder called when user clicks Start on a device row.
        Implement your actual device-start logic here or override this method in a subclass.
        """
        sig_value = {}
        if self.act_control_values[device_name] != {}:
            for key, value in self.act_control_values[device_name].items():
                signame = f"ACT_CTRL_{key}"
                sig_value[signame] = value

            self.frame_isct.send_signal_msg(sig_value)
            print(f"[Action] Start device {device_name} with signals {sig_value}")
        else:
            print(f"[ERROR] : No signal found for {device_name}")
    def stop_act_dvc(self, device_name: str):
        """
        Placeholder called when user clicks Stop on a device row.
        Implement your actual device-stop logic here or override this method in a subclass.
        """
        sig_value = {}
        if self.act_control_values[device_name] != {}:
            for key, value in self.act_control_values[device_name].items():
                signame = f"ACT_CTRL_{key}"
                sig_value[signame] = 0

            self.frame_isct.send_signal_msg(sig_value)
            print(f"[Action] Stop device {device_name}")

        else:
            print(f"[ERROR] : No signal found for {device_name}")

    # ----------------------- persistence helpers -----------------------
    def _save_graphs_state(self):
        try:
            tabs_state = []
            for i in range(self.tab_widget.count()):
                w = self.tab_widget.widget(i)
                # we only persist graph tabs that we created (they have _curves attr)
                if hasattr(w, '_curves'):
                    tabs_state.append({
                        'title': getattr(w, '_saved_tab_title', f'graph_{i}'),
                        'signals': list(w._curves.keys()),
                        'paused': getattr(w, '_paused', False)
                    })
            with open(self.graph_cfg_path, 'w') as fh:
                json.dump(tabs_state, fh, indent=2)
            print(f"[INFO] Graph state saved to {self.graph_cfg_path}")
        except Exception as e:
            print(f"[WARN] Failed to save graphs state: {e}")

    def _remove_tab_from_config(self, tab_title):
        try:
            # Charger l'existant
            try:
                with open(self.graph_cfg_path, 'r') as fh:
                    tabs_state = json.load(fh)
            except FileNotFoundError:
                tabs_state = []

            # Filtrer en excluant l'onglet supprimé
            new_tabs = [
                t for t in tabs_state
                if t.get("title") != tab_title
            ]

            # Sauvegarder la config nettoyée
            with open(self.graph_cfg_path, 'w') as fh:
                json.dump(new_tabs, fh, indent=2)

            print(f"[INFO] Tab '{tab_title}' removed from JSON")

        except Exception as e:
            print(f"[WARN] Failed to update tab state after removal: {e}")

    def _load_graphs_state(self):
        if not os.path.isfile(self.graph_cfg_path):
            return
        try:
            with open(self.graph_cfg_path, 'r') as fh:
                tabs_state = json.load(fh)
            for tab in tabs_state:
                title = tab.get('title', 'Graph')
                signals = tab.get('signals', [])
                widget = self.__open_graph_tab(title, saved_signals=signals)
                # if paused, flip paused flag
                if tab.get('paused', False):
                    widget._paused = True
            print(f"[INFO] Graph state restored from {self.graph_cfg_path}")
        except Exception as e:
            print(f"[WARN] Failed to restore graph state: {e}")

    def _save_act_controls(self):
        try:
            with open(self.act_ctrl_path, 'w') as fh:
                json.dump(self.act_control_values, fh, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to save actuator controls: {e}")

    def _load_act_controls(self):
        reset_json = False
        if not os.path.isfile(self.act_ctrl_path):
            return {key : {} for key in self.actuator.dvc_list}
        try:
            with open(self.act_ctrl_path, 'r') as fh:
                store_value = json.load(fh)
                
                for interface in store_value.values():
                    if reset_json:
                        break

                    for interface_id in interface.keys():
                        if interface_id not in self.actuator.info.keys():
                            reset_json = True
                            break
        except Exception as e:
            print(f"[WARN] Failed to load actuator controls: {e}")
            return {key : {} for key in self.actuator.dvc_list}
        
        if reset_json:
            print("[WARNING] : act_interface change, reset to default")
            return {key : {} for key in self.actuator.dvc_list}
        else:
            return store_value
        

    def __update_refresh_btn_color(self):
        color = "green" if self.is_ecu_connected else "red"
        self.btn_refresh.setStyleSheet(f"background-color: {color};")


    def __load_signal_cfg(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Signal CFG", "", "JSON Files (*.json);;All Files (*)")
        if fname:
            self.f_prj_cfg = fname
            self._update_cfg_json("signal_cfg", fname)
            self.__reload_all()

    def __load_excel_cfg(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Select Excel CFG", "", "Excel Files (*.xlsx *.xls);;All Files (*)")
        if fname:
            self.f_excel_cfg = fname
            self._update_cfg_json("excel_cfg", fname)
            self.__reload_all()

    def _update_cfg_json(self, key, value):
        try:
            cfg_path = "config.json"  # votre fichier json de config
            cfg = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r') as f:
                    cfg = json.load(f)
            cfg[key] = value
            with open(cfg_path, 'w') as f:
                json.dump(cfg, f, indent=2)
            print(f"[INFO] Updated {key} in config.json")
        except Exception as e:
            print(f"[WARN] Failed to update config.json: {e}")

    def __reload_all(self):
        """Fonction qui détruit et recrée toutes les tables, onglets et signaux"""
        # On ferme les onglets graphiques
        for i in reversed(range(self.tab_widget.count())):
            w = self.tab_widget.widget(i)
            self.tab_widget.removeTab(i)
            w.deleteLater()

        # Reload frame_isct avec le nouveau f_prj_cfg
        self.frame_isct = FrameMngmt(self.f_prj_cfg)

        # Recréation des onglets Messages, Sensors et Actuators
        self.signals_name = self.frame_isct.get_signal_list()
        self.signals_values = {
            signal_name: deque(maxlen=PLOT_MAX_POINT)
            for signal_name in self.signals_name
        }
        self.previous_values = {signal_name: -1 for signal_name in self.signals_name}

        self._init_messages_tab()
        self._init_sensors_tab()
        self._init_actuators_tab()


    def closeEvent(self, event):
        # save graphs state and act controls on exit
        self._save_graphs_state()
        self._save_act_controls()
        # kill all threads / cyclic
        try:
            self.kill_all_thread()
        except Exception:
            pass    
        super().closeEvent(event)


# If run as a script, create an app with dummy config paths (user to adjust)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    # replace with real paths
    project_cfg = 'path/to/prj_cfg'
    excel_cfg = 'path/to/excel_cfg.xlsx'
    w = SignalViewer(project_cfg, excel_cfg)
    w.show()
    sys.exit(app.exec_())

#------------------------------------------------------------------------------
#                             FUNCTION IMPLMENTATION
#------------------------------------------------------------------------------

    

    

#------------------------------------------------------------------------------
#		                    END OF FILE
#------------------------------------------------------------------------------
#--------------------------
# Function_name
#--------------------------

"""
    @brief
    @details

    @params[in]
    @params[out]
    @retval
"""

