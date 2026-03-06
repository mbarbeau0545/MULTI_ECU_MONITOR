from typing import Dict, Optional, Tuple

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QAction, QMainWindow, QMenu, QTabWidget, QWidget


class _DetachedTabWindow(QMainWindow):
    def __init__(self, manager: "DetachableTabManager", widget: QWidget, title: str) -> None:
        super().__init__(manager.owner_window)
        self._manager = manager
        self._tab_widget = manager.tab_widget
        self._widget = widget
        self._title = title
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowTitle(title)
        self.setCentralWidget(widget)
        self.resize(1000, 700)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._manager.reattach_window(self)
        super().closeEvent(event)


class DetachableTabManager:
    def __init__(self, tab_widget: QTabWidget, owner_window: QWidget) -> None:
        self.tab_widget = tab_widget
        self.owner_window = owner_window
        self._detached_windows: Dict[_DetachedTabWindow, Tuple[QWidget, str]] = {}

        bar = self.tab_widget.tabBar()
        bar.setContextMenuPolicy(Qt.CustomContextMenu)
        bar.customContextMenuRequested.connect(self._show_tab_context_menu)

    def _show_tab_context_menu(self, pos: QPoint) -> None:
        bar = self.tab_widget.tabBar()
        idx = bar.tabAt(pos)
        if idx < 0:
            return

        menu = QMenu(self.tab_widget)
        detach_action = QAction("Ouvrir dans une nouvelle fenetre", self.tab_widget)
        detach_action.triggered.connect(lambda: self.detach_tab(idx))
        menu.addAction(detach_action)
        menu.exec_(bar.mapToGlobal(pos))

    def detach_tab(self, index: int) -> Optional[_DetachedTabWindow]:
        if index < 0 or index >= self.tab_widget.count():
            return None
        widget = self.tab_widget.widget(index)
        title = self.tab_widget.tabText(index)
        if widget is None:
            return None
        self.tab_widget.removeTab(index)
        return self.detach_widget(widget, title)

    def detach_widget(self, widget: QWidget, title: str) -> _DetachedTabWindow:
        win = _DetachedTabWindow(self, widget, title)
        self._detached_windows[win] = (widget, title)
        win.show()
        return win

    def reattach_window(self, win: _DetachedTabWindow) -> None:
        data = self._detached_windows.pop(win, None)
        if data is None:
            return
        widget, title = data
        try:
            # Central widget must be detached from closing window before reparenting.
            win.takeCentralWidget()
            if self.tab_widget.indexOf(widget) < 0:
                self.tab_widget.addTab(widget, title)
                self.tab_widget.setCurrentWidget(widget)
        except RuntimeError:
            # Parent tab widget already destroyed, nothing to do.
            return
