import os
import runpy
import traceback
import json
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import List, Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from Protocole.CAN.Drivers.pcSim.pc_sim_client import PcSimClient

from .config import EcuConfig
from .script_runtime_api import ScriptApiBackend, clear_backend, set_backend


@dataclass
class _ScriptItem:
    name: str
    path: Path


class _ScriptWorker(QObject):
    finished = pyqtSignal(bool, str)
    log_line = pyqtSignal(str)

    def __init__(
        self,
        script_path: Path,
        client: PcSimClient,
        stop_event: Event,
        default_node: int,
        sym_file: Optional[Path],
    ) -> None:
        super().__init__()
        self.script_path = script_path
        self.client = client
        self.stop_event = stop_event
        self.default_node = default_node
        self.sym_file = sym_file

    def run(self) -> None:
        backend = ScriptApiBackend(
            self.client,
            self.stop_event,
            self.log_line.emit,
            self.default_node,
            sym_file=self.sym_file,
        )
        try:
            set_backend(backend)
            self.log_line.emit(f"[RUN] {self.script_path.name}")
            runpy.run_path(str(self.script_path), run_name="__main__")
            if self.stop_event.is_set():
                self.finished.emit(False, "stopped")
            else:
                self.finished.emit(True, "done")
        except Exception:
            self.finished.emit(False, traceback.format_exc())
        finally:
            clear_backend()


class ScriptRunnerTab(QWidget):
    def __init__(self, ecu: EcuConfig, cfg_path: Path) -> None:
        super().__init__()
        self.ecu = ecu
        self.cfg_path = cfg_path
        self.client = PcSimClient(host=ecu.udp.host, port=ecu.udp.port, timeout=ecu.udp.timeout_s)

        self._scripts: List[_ScriptItem] = []
        self._active_script_idx = -1

        self._thread: Optional[QThread] = None
        self._worker: Optional[_ScriptWorker] = None
        self._stop_event = Event()

        self.script_selector = QComboBox()
        self.path_lbl = QLabel("-")
        self.path_lbl.setStyleSheet("color: #666;")
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.status_lbl = QLabel("Idle")
        self.status_lbl.setStyleSheet("color: #666;")

        self._build_ui()
        self._scan_scripts()
        self._refresh_selector()
        if self._scripts:
            self._set_active_script(0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        row_manage = QHBoxLayout()
        row_manage.addWidget(QLabel("Script"))
        row_manage.addWidget(self.script_selector, 1)
        btn_new = QPushButton("New")
        btn_open = QPushButton("Open")
        btn_rename = QPushButton("Rename")
        btn_delete = QPushButton("Delete")
        btn_reload = QPushButton("Reload")
        row_manage.addWidget(btn_new)
        row_manage.addWidget(btn_open)
        row_manage.addWidget(btn_rename)
        row_manage.addWidget(btn_delete)
        row_manage.addWidget(btn_reload)
        root.addLayout(row_manage)

        row_info = QHBoxLayout()
        row_info.addWidget(QLabel("Path:"))
        row_info.addWidget(self.path_lbl, 1)
        btn_open_dir = QPushButton("Open Folder")
        row_info.addWidget(btn_open_dir)
        root.addLayout(row_info)

        row_run = QHBoxLayout()
        btn_run = QPushButton("Run")
        btn_stop = QPushButton("Stop")
        row_run.addWidget(btn_run)
        row_run.addWidget(btn_stop)
        row_run.addWidget(self.status_lbl)
        row_run.addStretch(1)
        root.addLayout(row_run)

        split = QSplitter()
        split.addWidget(self.preview)
        split.addWidget(self.log_view)
        split.setSizes([700, 260])
        root.addWidget(split, 1)

        self.script_selector.currentIndexChanged.connect(self._on_script_selected)
        btn_new.clicked.connect(self._on_new_script)
        btn_open.clicked.connect(self._on_open_script)
        btn_rename.clicked.connect(self._on_rename_script)
        btn_delete.clicked.connect(self._on_delete_script)
        btn_reload.clicked.connect(self._on_reload)
        btn_open_dir.clicked.connect(self._on_open_scripts_folder)
        btn_run.clicked.connect(self._on_run_script)
        btn_stop.clicked.connect(self._on_stop_script)

    def _scripts_dir(self) -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in self.ecu.name)
        path = self.cfg_path.parent / "scripts" / safe_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _legacy_scripts_json_path(self) -> Path:
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in self.ecu.name)
        return self.cfg_path.parent / f"{self.cfg_path.stem}_{safe_name}_scripts.json"

    def _default_script_text(self) -> str:
        return (
            "from app.script_runtime_api import log\n"
            "from app.script_api_head_cutter import send_hc_joint, get_hc_feedback\n"
            "\n"
            "# High-level HeadCutter API\n"
            "send_hc_joint(alpha_b_mrad=1000, alpha_c_mrad=900, knife_rpm=20, cntr_knife_rpm=20, pos_id=1, node=1)\n"
            "\n"
            "fb = get_hc_feedback(timeout_ms=50)\n"
            "log(f\"feedback={fb}\")\n"
        )

    def _ensure_default_script_exists(self) -> None:
        self._migrate_legacy_json_scripts()
        script_path = self._scripts_dir() / "trajectory_demo.py"
        if script_path.exists():
            return
        script_path.write_text(self._default_script_text(), encoding="utf-8")

    def _migrate_legacy_json_scripts(self) -> None:
        legacy_path = self._legacy_scripts_json_path()
        if not legacy_path.exists():
            return
        try:
            raw = json.loads(legacy_path.read_text(encoding="utf-8-sig"))
            scripts_raw = raw.get("scripts", [])
            if not isinstance(scripts_raw, list):
                return
            created = 0
            for item in scripts_raw:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                code = str(item.get("code", ""))
                if not name:
                    continue
                safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)
                dst = self._scripts_dir() / f"{safe_name}.py"
                if dst.exists():
                    continue
                if "from app.script_runtime_api import *" not in code:
                    code = "from app.script_runtime_api import *\n\n" + code
                dst.write_text(code, encoding="utf-8")
                created += 1
            if created > 0:
                self._append_log(f"[MIGRATE] {created} legacy scripts imported from {legacy_path.name}")
        except Exception:
            return

    def _scan_scripts(self) -> None:
        self._ensure_default_script_exists()
        self._scripts = []
        for script_path in sorted(self._scripts_dir().glob("*.py"), key=lambda p: p.name.lower()):
            self._scripts.append(_ScriptItem(name=script_path.stem, path=script_path))

    def _refresh_selector(self) -> None:
        self.script_selector.blockSignals(True)
        self.script_selector.clear()
        for s in self._scripts:
            self.script_selector.addItem(s.name)
        self.script_selector.blockSignals(False)

    def _set_active_script(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._scripts):
            self._active_script_idx = -1
            self.path_lbl.setText("-")
            self.preview.clear()
            return
        self._active_script_idx = idx
        self.script_selector.setCurrentIndex(idx)
        script = self._scripts[idx]
        self.path_lbl.setText(str(script.path))
        try:
            self.preview.setPlainText(script.path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            self.preview.setPlainText(f"# Cannot load script:\n# {exc}")

    def _on_script_selected(self, idx: int) -> None:
        self._set_active_script(idx)

    def _script_name_is_used(self, name: str) -> bool:
        lowered = name.lower()
        return any(item.name.lower() == lowered for item in self._scripts)

    def _on_new_script(self) -> None:
        name, ok = QInputDialog.getText(self, "New Script", "Script name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if self._script_name_is_used(name):
            QMessageBox.warning(self, "Script Runner", f"Script '{name}' already exists.")
            return
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)
        path = self._scripts_dir() / f"{safe_name}.py"
        path.write_text(self._default_script_text(), encoding="utf-8")
        self._scan_scripts()
        self._refresh_selector()
        for idx, item in enumerate(self._scripts):
            if item.path == path:
                self._set_active_script(idx)
                break
        self._append_log(f"[NEW] {path.name}")

    def _on_open_script(self) -> None:
        if self._active_script_idx < 0:
            return
        path = self._scripts[self._active_script_idx].path
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except Exception:
            QMessageBox.information(self, "Script Runner", f"Open this file in your IDE:\n{path}")

    def _on_rename_script(self) -> None:
        if self._active_script_idx < 0:
            return
        current = self._scripts[self._active_script_idx]
        name, ok = QInputDialog.getText(self, "Rename Script", "New name:", text=current.name)
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)
        if self._script_name_is_used(safe_name) and safe_name.lower() != current.name.lower():
            QMessageBox.warning(self, "Script Runner", f"Script '{safe_name}' already exists.")
            return
        new_path = current.path.with_name(f"{safe_name}.py")
        try:
            current.path.rename(new_path)
        except Exception as exc:
            QMessageBox.warning(self, "Script Runner", str(exc))
            return
        self._scan_scripts()
        self._refresh_selector()
        for idx, item in enumerate(self._scripts):
            if item.path == new_path:
                self._set_active_script(idx)
                break
        self._append_log(f"[RENAME] {current.path.name} -> {new_path.name}")

    def _on_delete_script(self) -> None:
        if self._active_script_idx < 0:
            return
        if len(self._scripts) <= 1:
            QMessageBox.warning(self, "Script Runner", "At least one script must remain.")
            return
        current = self._scripts[self._active_script_idx]
        answer = QMessageBox.question(self, "Delete Script", f"Delete '{current.path.name}'?")
        if answer != QMessageBox.Yes:
            return
        try:
            current.path.unlink()
        except Exception as exc:
            QMessageBox.warning(self, "Script Runner", str(exc))
            return
        self._scan_scripts()
        self._refresh_selector()
        self._set_active_script(min(self._active_script_idx, len(self._scripts) - 1))
        self._append_log(f"[DELETE] {current.path.name}")

    def _on_reload(self) -> None:
        old_path = self._scripts[self._active_script_idx].path if self._active_script_idx >= 0 else None
        self._scan_scripts()
        self._refresh_selector()
        if old_path is not None:
            for idx, item in enumerate(self._scripts):
                if item.path == old_path:
                    self._set_active_script(idx)
                    break
            else:
                if self._scripts:
                    self._set_active_script(0)
        elif self._scripts:
            self._set_active_script(0)
        self._append_log("[RELOAD] script list refreshed")

    def _on_open_scripts_folder(self) -> None:
        folder = self._scripts_dir()
        try:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except Exception:
            _ = QFileDialog.getExistingDirectory(self, "Scripts Folder", str(folder))

    def _append_log(self, line: str) -> None:
        self.log_view.appendPlainText(line)
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_view.setTextCursor(cursor)

    def _set_running_state(self, is_running: bool, text: str) -> None:
        self.status_lbl.setText(text)
        self.status_lbl.setStyleSheet("color: #005a9e;" if is_running else "color: #666;")

    def _on_run_script(self) -> None:
        if self._thread is not None:
            QMessageBox.warning(self, "Script Runner", "A script is already running.")
            return
        if self._active_script_idx < 0:
            return
        script = self._scripts[self._active_script_idx]
        if not script.path.exists():
            QMessageBox.warning(self, "Script Runner", f"Missing script file:\n{script.path}")
            return

        self._stop_event.clear()
        self._worker = _ScriptWorker(script.path, self.client, self._stop_event, self.ecu.udp.node, self.ecu.sym_file)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.log_line.connect(self._append_log)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._set_running_state(True, "Running")
        self._thread.start()

    def _on_stop_script(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._append_log("[STOP] requested")

    def _on_worker_finished(self, success: bool, details: str) -> None:
        if success:
            self._append_log("[DONE] script finished")
        else:
            self._append_log(f"[ERROR] {details}")
        self._set_running_state(False, "Idle")
        self._worker = None
        self._thread = None

    def shutdown(self) -> None:
        if self._thread is not None:
            self._stop_event.set()
            self._thread.quit()
            self._thread.wait(1000)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.shutdown()
        super().closeEvent(event)
