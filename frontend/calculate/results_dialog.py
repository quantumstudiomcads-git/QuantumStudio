"""Read-only Calculate Result browser; parsing stays in the Qt-free service."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout


class _ParseThread(QThread):
    finished_result = Signal(object)
    failed = Signal(str)
    def __init__(self, service, root, execution_id, reparse, parent=None):
        super().__init__(parent); self.service=service; self.root=root; self.execution_id=execution_id; self.reparse=reparse
    def run(self):
        try: self.finished_result.emit(self.service.parse(self.root,self.execution_id,reparse=self.reparse))
        except Exception as error: self.failed.emit(str(error))


class ResultsDialog(QDialog):
    def __init__(self, service, workflow_root, parent=None):
        super().__init__(parent); self.service=service; self.root=workflow_root; self._thread=None
        self.setWindowTitle("Calculation Results"); layout=QVBoxLayout(self)
        header=QHBoxLayout(); header.addWidget(QLabel("Execution:")); self.execution=QComboBox(self)
        for execution_id in service.executions(workflow_root): self.execution.addItem(execution_id[-12:],execution_id)
        self.execution.currentIndexChanged.connect(self.refresh); header.addWidget(self.execution,1); layout.addLayout(header)
        self.state=QLabel(self); layout.addWidget(self.state)
        self.detail=QPlainTextEdit(self); self.detail.setReadOnly(True); layout.addWidget(self.detail,1)
        actions=QHBoxLayout(); self.parse=QPushButton("Parse Results",self); self.reparse=QPushButton("Re-parse",self)
        self.parse.clicked.connect(lambda:self._parse(False)); self.reparse.clicked.connect(lambda:self._parse(True)); actions.addWidget(self.parse); actions.addWidget(self.reparse); actions.addStretch(); layout.addLayout(actions)
        self.resize(720,500); self.refresh()
    def refresh(self):
        if self.execution.count()==0: self.state.setText("No execution attempts are stored for this workflow."); self.detail.setPlainText(""); self.parse.setEnabled(False); self.reparse.setEnabled(False); return
        execution_id=self.execution.currentData(); rows=self.service.summaries(self.root,execution_id)
        self.state.setText("Results not parsed." if not rows else f"{len(rows)} parsed result(s).")
        self.detail.setPlainText("\n\n".join(f"{row['type']} — {row['status']}\n{row['summary']}\nParser: {row['provenance'].parser_id if row['provenance'] else 'unavailable'}\nSources: {', '.join(row['provenance'].source_paths) if row['provenance'] else 'unavailable'}" for row in rows))
        self.parse.setEnabled(True); self.reparse.setEnabled(bool(rows))
    def _parse(self,reparse):
        if self._thread is not None: return
        self.parse.setEnabled(False); self.reparse.setEnabled(False); self.state.setText("Parsing results…")
        self._thread=_ParseThread(self.service,self.root,self.execution.currentData(),reparse,self)
        self._thread.finished_result.connect(self._parsed); self._thread.failed.connect(self._failed); self._thread.start()
    def _parsed(self,result):
        errors=result.get("errors",()); self._thread.wait(); self._thread=None; self.refresh()
        if errors: self.state.setText("Parsed with warnings: " + "; ".join(errors))
    def _failed(self,message):
        self._thread.wait(); self._thread=None; self.state.setText("Parse Failed: " + message); self.parse.setEnabled(True); self.reparse.setEnabled(True)
