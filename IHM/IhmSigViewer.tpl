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
import sys
import os
from collections import deque
import sys, time
import os
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTableWidget, QTableWidgetItem, QPushButton,
    QVBoxLayout, QWidget, QTabWidget, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QScrollArea, QFrame, QAction, QMenu
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QBrush, QFontMetrics

import pyqtgraph as pg


from Frame.frameMngmt import FrameMngmt
from Signal.ActSnsMngmt import ActInfo, SnsInfo
from typing import List, Dict
#------------------------------------------------------------------------------
#                                       CONSTANT
#------------------------------------------------------------------------------
REFRESH_IMH_SECONDS = 20
PLOT_MAX_POINT = 2000
# CAUTION : Automatic generated code section: Start #

# CAUTION : Automatic generated code section: End #
#------------------------------------------------------------------------------
#                                       CLASS
#------------------------------------------------------------------------------

class SignalViewer(QMainWindow):
    def __init__(self, f_prj_cfg: str, f_excel_cfg: str):
        super().__init__()

        # init frame instance
        self.frame_isct = FrameMngmt(f_prj_cfg)
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

        self.frame_isct.get_symbol_list()

        # ========================
        # Création du QTabWidget
        # ========================
        self.tab_widget = QTabWidget()

        # --- Onglet "Signals" ---
        self.signals_widget = QWidget()
        self.signals_layout = QVBoxLayout(self.signals_widget)

        self.table = QTableWidget(len(self.signals_name), 4)
        self.table.setHorizontalHeaderLabels(["Signal", "Raw Value", "Value", "Graph"])
        self.table.setColumnWidth(2, 150)  # colonne Value
        self.table.setColumnWidth(0, 150)  # colonne Signal
        self.signals_layout.addWidget(self.table)

        self.tab_widget.addTab(self.signals_widget, "Signals")

        # --- Onglet "Message Sender" ---
        self.msg_sender_widget = QWidget()
        self.msg_sender_layout = QVBoxLayout(self.msg_sender_widget)

        # --- Onglet "Sensors" ---
        self.sensors = SnsInfo(f_excel_cfg)
        self.sensors_widget = QWidget()
        # --- Onglet "Actuators" ---
        self.actuator = ActInfo(f_excel_cfg)
        self.actuators_widget = QWidget()

        btn_add_msg = QPushButton("Add message")
        btn_add_msg.clicked.connect(self.__add_message_row)
        self.msg_sender_layout.addWidget(btn_add_msg)

        # ScrollArea qui contiendra les messages
        self.msg_scroll = QScrollArea()
        self.msg_scroll.setWidgetResizable(True)
        self.msg_container = QWidget()
        self.msg_rows_container = QVBoxLayout(self.msg_container)
        self.msg_container.setLayout(self.msg_rows_container)

        self.msg_scroll.setWidget(self.msg_container)
        self.msg_sender_layout.addWidget(self.msg_scroll)

        self.tab_widget.addTab(self.msg_sender_widget, "Message Sender")

        # === Ajout du tab_widget comme contenu principal ===
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.tab_widget)
        self.setCentralWidget(container)

        # ========================
        # Remplissage de la table Signals
        # ========================
        for row, signal_name in enumerate(self.signals_name):
            self.table.setItem(row, 0, QTableWidgetItem(signal_name))
            # Bouton Graph
            btn = QPushButton("Graph")
            btn.clicked.connect(lambda _, s=signal_name: self.__open_graph_tab(s))
            self.table.setCellWidget(row, 3, btn)

        # ========================
        # Timers de mise à jour
        # ========================
        self.__connect_ecu()
        self.timer = QTimer()
        self.timer.timeout.connect(self.__refresh_table)
        self.timer.start(REFRESH_IMH_SECONDS)  # 50 ms

        # timer de garde (évite freeze de l’UI si pas de signal)
        self._timer_interrupt = QTimer()
        self._timer_interrupt.start(REFRESH_IMH_SECONDS)
        self._timer_interrupt.timeout.connect(lambda: None)


    #--------------------------
    # kill_all_thread
    #--------------------------
    def kill_all_thread(self):
        """Kill all thread currently on going 
        """
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
     #--------------------------
    # __refresh_table
    #--------------------------
    def __refresh_table(self):
        curr_time = time.time()
        if not self.is_ecu_connected and\
            (curr_time - self.last_try_con) > 5: # 5sec
            self.__connect_ecu()

        else:
            for row, signal_name in enumerate(self.signals_name):
                sig_val = self.frame_isct.get_signal_value(signal_name)
                if sig_val == [[]]:
                    continue

                # >>> au lieu d’écraser, on empile dans une deque
                for sig_info in sig_val:
                    if sig_info:
                        self.signals_values[signal_name].append(sig_info)

                # Mise à jour table (affiche la dernière valeur reçue)
                if sig_val and sig_val[-1]:
                    raw_val = str(sig_val[-1][0])
                    calc_val = str(sig_val[-1][1])
                    prev_raw = self.previous_values.get(signal_name)

                    item_raw = QTableWidgetItem(raw_val)
                    item_calc = QTableWidgetItem(calc_val)
                    item_raw.setForeground(QBrush(QColor('black')))
                    item_calc.setForeground(QBrush(QColor('black')))
                    self.table.setItem(row, 1, item_raw)
                    self.table.setItem(row, 2, item_calc)

                    if prev_raw is not None and prev_raw != raw_val:
                        item_raw.setBackground(QColor("yellow"))
                        item_calc.setBackground(QColor("yellow"))
                    else:
                        item_raw.setBackground(QColor("white"))
                        item_calc.setBackground(QColor("white"))

                    self.previous_values[signal_name] = raw_val

    #--------------------------
    # __open_graph_tab
    #--------------------------
    #--------------------------
    # __open_graph_tab
    #--------------------------
    def __open_graph_tab(self, signal_name):
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

        # Ajouter le premier signal
        self.__add_signal_to_tab(widget, signal_name)

        # Fonction update
        def update_plot():
            if widget._paused:
                return

            # init t0 commun
            if widget._t0 is None:
                min_t0 = None
                for sig_name in widget._curves.keys():
                    if self.signals_values[sig_name]:
                        t0_candidate = self.signals_values[sig_name][0][2]
                        if min_t0 is None or t0_candidate < min_t0:
                            min_t0 = t0_candidate
                widget._t0 = min_t0
                if widget._t0 is None:
                    return

            # mise à jour par signal
            for sig_name, sig_data in widget._curves.items():
                while self.signals_values[sig_name]:
                    raw, calc, ts = self.signals_values[sig_name][0]
                    if ts < widget._t0:
                        self.signals_values[sig_name].popleft()
                        continue

                    t_sec = (ts - widget._t0) / 1e9
                    if not sig_data["times"] or t_sec > sig_data["times"][-1]:
                        sig_data["times"].append(t_sec)
                        sig_data["values"].append(raw)
                    self.signals_values[sig_name].popleft()

                # découpe et affichage
                if len(sig_data["times"]) > PLOT_MAX_POINT:
                    sig_data["times"] = sig_data["times"][-PLOT_MAX_POINT:]
                    sig_data["values"] = sig_data["values"][-PLOT_MAX_POINT:]

                if len(sig_data["times"]) > 1:
                    sig_data["curve"].setData(sig_data["times"], sig_data["values"])

        # Timer Qt
        timer = QTimer(widget)
        timer.timeout.connect(update_plot)
        timer.start(REFRESH_IMH_SECONDS)
        widget._timer = timer

    #--------------------------
    # __add_signal_to_tab
    #--------------------------
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

    #--------------------------
    # __remove_signal_from_tab
    #--------------------------
    def __remove_signal_from_tab(self, widget, signal_name: str):
        if signal_name in widget._curves:
            widget._plot_widget.removeItem(widget._curves[signal_name]["curve"])
            del widget._curves[signal_name]
      #--------------------------
    # __show_graph_context_menu
    #--------------------------
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
        available = [s for s in self.signals_name if s not in widget._curves]
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
    #--------------------------
    # __close_tab
    #--------------------------
    def __close_tab(self, f_widget):
        index = self.tab_widget.indexOf(f_widget)
        if index != -1:
            self.tab_widget.removeTab(index)
            f_widget._timer.stop()  # stop timer for this graph
            f_widget.deleteLater()

    def __toggle_pause(self, f_widget, f_btn_toggle):
        f_widget._paused = not f_widget._paused
        f_btn_toggle.setText("Start" if f_widget._paused else "Stop")
    #--------------------------
    # __add_message_row
    #--------------------------
    def __add_message_row(self):
        """Ajoute une ligne pour configurer un message"""
        # === Conteneur visuel (cadre avec bordure) ===
        row_widget = QFrame()
        row_widget.setFrameShape(QFrame.StyledPanel)
        row_widget.setFrameShadow(QFrame.Raised)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(10, 5, 10, 5)
        row_layout.setSpacing(15)

        # === Sélecteur du symbole ===
        combo = QComboBox()
        combo.addItems(self.frame_isct.get_symbol_list())
        combo.setMinimumWidth(180)
        row_layout.addWidget(combo)

        # === Table des signaux ===
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

        # Remplissage initial si des symboles existent
        if combo.count() > 0:
            self.__populate_signals(sig_table, combo.currentText())

        combo.currentTextChanged.connect(
            lambda sym: self.__populate_signals(sig_table, sym)
        )

        # === Paramètres en colonne droite ===
        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)

        # Cyclic send
        cyc_layout = QHBoxLayout()
        cyc_layout.addWidget(QLabel("Cyclic (ms):"))
        cyclic_edit = QLineEdit("0")
        cyclic_edit.setFixedWidth(60)
        cyc_layout.addWidget(cyclic_edit)
        right_layout.addLayout(cyc_layout)

        # Bouton Send
        btn_send = QPushButton("Send")
        btn_send.setFixedWidth(70)
        right_layout.addWidget(btn_send)

        btn_send.clicked.connect(
            lambda _, cb=combo, st=sig_table, ce=cyclic_edit, rw=row_widget:
                self.__send_message(cb.currentText(), st, ce.text(), rw)
        )

        # Bouton Delete
        btn_delete = QPushButton("Delete")
        btn_delete.setFixedWidth(70)
        btn_delete.setStyleSheet("background-color: #f28b82;")
        right_layout.addWidget(btn_delete)

        btn_delete.clicked.connect(lambda _, rw=row_widget: self.__delete_message_row(rw))

        # Espacement en bas
        right_layout.addStretch()
        row_layout.addLayout(right_layout)

        # Ajouter le tout dans la zone scrollable
        self.msg_rows_container.addWidget(row_widget)

    #--------------------------
    # __populate_signals
    #--------------------------
    def __populate_signals(self, table: QTableWidget, sym_name: str):
        """Remplit la table des signaux pour le message choisi"""
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

        # Calcul largeur colonne signal
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

            # Mesure largeur
            width = metrics.horizontalAdvance(text) + 20  # + marge
            if width > max_width:
                max_width = width

        # Ajuster la largeur de la colonne signal
        table.setColumnWidth(0, max_width)

        # Ajuster hauteur table
        header_height = table.horizontalHeader().height()
        visible_rows = min(len(signals), max_visible_rows)
        table.setFixedHeight(header_height + row_height * visible_rows)

        # Scroll selon le nombre de lignes
        table.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if len(signals) <= max_visible_rows else Qt.ScrollBarAsNeeded
        )



    #--------------------------
    # __delete_message_row
    #--------------------------
    def __delete_message_row(self, row_widget: QWidget):
        """Supprime une ligne message (UI + timer éventuel)"""
        # Si on a attaché un timer pour cyclic send, on l'arrête
        if hasattr(row_widget, "_timer") and row_widget._timer is not None:
            row_widget._timer.stop()
            row_widget._timer.deleteLater()

        # Supprime le widget du layout et détruit
        self.msg_rows_container.removeWidget(row_widget)
        row_widget.deleteLater()
        
    #--------------------------
    # __send_message
    #--------------------------
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

        cyclic_val = int(cyclic_val) if cyclic_val.isdigit() else 0
        if cyclic_val > 0:
            print(f"[Cyclic] Send {sym_name} every {cyclic_val}ms with {signals}")
            timer = QTimer(row_widget)
            timer.timeout.connect(lambda: self.frame_isct.send_signal_msg(sym_name, signals))
            timer.start(cyclic_val)
            row_widget._timer = timer
        else:
            print(f"[Once] Send {sym_name} with {signals}")
            self.frame_isct.send_signal_msg(sym_name, signals)
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

