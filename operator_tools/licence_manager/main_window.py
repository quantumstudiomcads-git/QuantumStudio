"""Local-only administrative interface; no web server or customer UI integration."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QMainWindow,
    QMessageBox, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget)

from .audit import current_operator_id, verify_chain
from .crypto import DataProtector
from .database import Database
from .exports import export_licence
from .imports import import_activation_json, import_applicants_json
from .issuance import authorize_activation_profile, issue_for_request_for_testing, record_expiries, revoke_licence
from .paths import data_root
from .signing import ProductionAuthority, TestEphemeralAuthority, public_key_record, record_public_metadata
from .models import Profile
from PySide6.QtSvgWidgets import QSvgWidget


class LicenceManagerWindow(QMainWindow):
    def __init__(self, *, test_mode=False, database=None, authority=None, data_root_override=None):
        super().__init__()
        self.setWindowTitle("Quantum Studio Licence Manager")
        self.resize(1180, 760)
        self.test_mode = bool(test_mode)
        self.operator_id = current_operator_id()
        self._temporary = None
        if database is None:
            if self.test_mode:
                self._temporary = tempfile.TemporaryDirectory(prefix="qs-lm-test-")
                protector = DataProtector.for_testing(os.urandom(32))
                root = data_root_override or self._temporary.name
            else:
                root = data_root(data_root_override)
                protector = DataProtector.from_windows_keyfile(root / "data-key.dpapi")
            database = Database(root, protector)
        self.database = database
        self.authority = authority or (TestEphemeralAuthority() if self.test_mode else ProductionAuthority(
            data_root(data_root_override) / "licence-signing-key.dpapi", data_root(data_root_override) / "licence-signing-public.json", database=database))
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        self.setStyleSheet("QMainWindow,QWidget{background:#f5f8fb;color:#183247;font-family:'Segoe UI';font-size:10pt} QLabel#title{font-size:19pt;font-weight:600;color:#103c59} QListWidget{background:white;border:1px solid #d6e2e9;border-radius:6px;padding:5px} QListWidget::item{padding:10px} QListWidget::item:selected{background:#dff5fa;color:#075d77} QPushButton{background:#087f9b;color:white;border:0;border-radius:5px;padding:8px 13px} QPushButton:disabled{background:#9aadb8} QTableWidget,QTextEdit{background:white;border:1px solid #d6e2e9;border-radius:5px}")
        root = QWidget(); layout = QVBoxLayout(root)
        head = QHBoxLayout()
        brand_mark = QSvgWidget(str(Path(__file__).resolve().parents[2] / "assets" / "quantum-studio-v0.1.svg"))
        brand_mark.setFixedSize(44, 40)
        head.addWidget(brand_mark)
        logo = QLabel("◈  Quantum Studio")
        logo.setStyleSheet("font-size:15pt;font-weight:600;color:#087f9b")
        title = QLabel("Licence Manager"); title.setObjectName("title")
        head.addWidget(logo); head.addStretch(1); head.addWidget(title); layout.addLayout(head)
        mode = "TEST MODE — ephemeral signing only; files and licences are test data" if self.test_mode else "PRODUCTION MODE — operator workstation"
        self.mode_banner = QLabel(mode)
        self.mode_banner.setStyleSheet("background:#fff0c2;color:#704800;padding:9px;border-radius:4px;font-weight:600")
        layout.addWidget(self.mode_banner)
        status = self.authority.status()
        from .audit import append_event
        with self.database.transaction() as db:
            append_event(db, "signing_authority_status", self.operator_id, [], {"available": status.available, "mode": status.mode})
        self.authority_banner = QLabel("SIGNING AUTHORITY UNAVAILABLE" if not status.available else f"Signing authority available · {status.mode} · {status.kid}")
        self.authority_banner.setStyleSheet("background:#ffe3e3;color:#842525;padding:9px;border-radius:4px;font-weight:600" if not status.available else "background:#dff5e9;color:#145c39;padding:9px;border-radius:4px")
        layout.addWidget(self.authority_banner)
        body = QHBoxLayout(); self.nav = QListWidget(); self.nav.addItems(["Dashboard", "Applications", "Application Details", "Activation Requests", "Issue Licence", "Licences", "Audit Log", "Settings / Signing Authority"])
        self.pages = QStackedWidget(); body.addWidget(self.nav, 1); body.addWidget(self.pages, 4); layout.addLayout(body)
        self.page_widgets = {}
        for name in [self.nav.item(i).text() for i in range(self.nav.count())]:
            page = QWidget(); page_layout = QVBoxLayout(page)
            page_layout.addWidget(QLabel(name))
            if name == "Dashboard":
                self.dashboard = QTextEdit(); self.dashboard.setReadOnly(True); page_layout.addWidget(self.dashboard)
            elif name in {"Applications", "Activation Requests", "Licences", "Audit Log"}:
                table = QTableWidget(); table.setColumnCount(1); table.setHorizontalHeaderLabels([name]); table.horizontalHeader().setStretchLastSection(True); page_layout.addWidget(table)
                setattr(self, self._attr(name), table)
                actions = QHBoxLayout()
                if name == "Applications":
                    for label, callback in (("Import website applications…", self.import_applicants), ("Review selected", lambda: self.transition_selected("UNDER_REVIEW")), ("Approve selected", lambda: self.transition_selected("APPROVED")), ("Reject selected…", lambda: self.transition_selected("REJECTED")), ("Details", self.show_selected_details)):
                        button = QPushButton(label); button.clicked.connect(callback); actions.addWidget(button)
                elif name == "Activation Requests":
                    button = QPushButton("Import activation request…"); button.clicked.connect(self.import_activation); actions.addWidget(button)
                elif name == "Licences":
                    button = QPushButton("Revoke selected…"); button.clicked.connect(self.revoke_selected); actions.addWidget(button)
                    button = QPushButton("Export selected…"); button.clicked.connect(self.export_selected); actions.addWidget(button)
                elif name == "Audit Log":
                    button = QPushButton("Verify audit chain"); button.clicked.connect(self.verify_audit); actions.addWidget(button)
                page_layout.addLayout(actions)
            elif name == "Application Details":
                self.details = QTextEdit(); self.details.setReadOnly(True); page_layout.addWidget(self.details)
            elif name == "Issue Licence":
                page_layout.addWidget(QLabel("Select an imported activation request, authorize a local profile, then issue the device-bound licence."))
                button = QPushButton("Authorize profile and issue selected request…"); button.clicked.connect(self.issue_selected); page_layout.addWidget(button)
            else:
                self.settings = QTextEdit(); self.settings.setReadOnly(True); page_layout.addWidget(self.settings)
                button = QPushButton("Export signing public key…"); button.clicked.connect(self.export_public_key); page_layout.addWidget(button)
            self.page_widgets[name] = page; self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex); self.nav.setCurrentRow(0)
        self.setCentralWidget(root)

    @staticmethod
    def _attr(name): return {"Applications": "applications_table", "Activation Requests": "requests_table", "Licences": "licences_table", "Audit Log": "audit_table"}[name]

    def refresh(self):
        db = self.database.connection
        record_expiries(self.database, operator_id=self.operator_id)
        self._fill(self.applications_table, db, "SELECT application_id,status FROM applicants ORDER BY imported_at DESC", ("Application ID", "Status"))
        self._fill(self.requests_table, db, "SELECT request_id,application_id,authorized_profile FROM activation_requests ORDER BY imported_at DESC", ("Request ID", "Application ID", "Operator-authorized profile"))
        self._fill(self.licences_table, db, "SELECT licence_id,profile,expires_at,revoked_at FROM licences ORDER BY issued_at DESC", ("Licence ID", "Profile", "Expires", "Revoked"))
        self._fill(self.audit_table, db, "SELECT timestamp,event_type,operator_id,event_hash FROM audit_events ORDER BY seq DESC", ("Timestamp", "Event", "Operator", "Hash"))
        counts = {state: db.execute("SELECT COUNT(*) FROM applicants WHERE status=?", (state,)).fetchone()[0] for state in ("APPLIED", "UNDER_REVIEW")}
        awaiting_activation = db.execute("SELECT COUNT(*) FROM applicants a WHERE a.status='APPROVED' AND NOT EXISTS (SELECT 1 FROM activation_requests r WHERE r.application_id=a.application_id)").fetchone()[0]
        now = int(datetime.now(timezone.utc).timestamp())
        expiring = db.execute("SELECT COUNT(*) FROM licences WHERE revoked_at IS NULL AND expires_at BETWEEN ? AND ?", (now, now + 30 * 86400)).fetchone()[0]
        expired_licences = db.execute("SELECT COUNT(*) FROM licences WHERE revoked_at IS NULL AND expires_at<=?", (now,)).fetchone()[0]
        revoked_licences = db.execute("SELECT COUNT(*) FROM licences WHERE revoked_at IS NOT NULL").fetchone()[0]
        status = self.authority.status()
        from .audit import append_event
        with self.database.transaction() as audit_db:
            append_event(audit_db, "signing_authority_status", self.operator_id, [], {"available": status.available, "mode": status.mode})
        awaiting = counts["APPLIED"] + db.execute("SELECT COUNT(*) FROM applicants WHERE status='UNDER_REVIEW'").fetchone()[0]
        self.dashboard.setPlainText(f"Applications awaiting review: {awaiting}\nApproved applicants awaiting activation: {awaiting_activation}\nLicences expiring within 30 days: {expiring}\nExpired licences: {expired_licences}\nRevoked licences: {revoked_licences}\nSigning authority: {status.message}")
        self.settings.setPlainText(f"Mode: {status.mode}\nStatus: {status.message}\nKey ID: {status.kid or '—'}\nFingerprint: {status.public_key_fingerprint or '—'}\nProduction key initialization is intentionally unavailable in this release.\nLicence trust is separate from updater signing.")

    @staticmethod
    def _fill(table, db, query, headers):
        if table.columnCount() != len(headers): table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        data = db.execute(query).fetchall()
        table.setRowCount(len(data))
        for r, row in enumerate(data):
            for c, value in enumerate(row): table.setItem(r, c, QTableWidgetItem(str(value or "")))

    def _refresh_tables(self):
        self.refresh()

    def import_applicants(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import version 1 website application export", "", "JSON (*.json)")
        if not path: return
        try:
            count = import_applicants_json(Path(path).read_bytes(), self.database, operator_id=self.operator_id)
            QMessageBox.information(self, "Import complete", f"Imported {count} new application(s).")
            self.refresh()
        except Exception as error: QMessageBox.critical(self, "Import failed", str(error))

    def import_activation(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Quantum Studio activation request", "", "JSON (*.json)")
        if not path: return
        try:
            imported = import_activation_json(Path(path).read_bytes(), self.database, operator_id=self.operator_id)
            QMessageBox.information(self, "Activation request", "Request imported." if imported else "Identical request was already imported.")
            self.refresh()
        except Exception as error: QMessageBox.critical(self, "Import failed", str(error))

    def _selected_id(self, table, column=0):
        row = table.currentRow()
        item = table.item(row, column) if row >= 0 else None
        return item.text() if item else None

    def transition_selected(self, state):
        app_id = self._selected_id(self.applications_table)
        if not app_id: return
        if state == "REJECTED" and QMessageBox.question(self, "Reject application", "Reject this applicant? This action is audited.") != QMessageBox.Yes: return
        try:
            from .models import ApplicantStatus
            self.database.transition(app_id, ApplicantStatus(state), operator_id=self.operator_id,
                                     note_code="rejected_by_operator" if state == "REJECTED" else "approved_by_operator" if state == "APPROVED" else "manual_review")
            self.refresh()
        except Exception as error: QMessageBox.warning(self, "Application was not changed", str(error))

    def show_selected_details(self):
        app_id = self._selected_id(self.applications_table)
        if not app_id: return
        self.details.setPlainText(json.dumps(self.database.applicant_pii(app_id), indent=2, ensure_ascii=False))
        self.nav.setCurrentRow(2)

    def issue_selected(self):
        request_id = self._selected_id(self.requests_table)
        if not request_id: QMessageBox.information(self, "Issue licence", "Select an activation request first."); return
        profiles = ["PROFESSOR_BETA", "INTERNAL_VALIDATION"]
        selected, ok = QInputDialog.getItem(self, "Authorize entitlement profile", "Select the local operator-approved profile:", profiles, 0, False)
        if not ok: return
        confirmation = "Authorize the 90-day PROFESSOR_BETA profile?" if selected == "PROFESSOR_BETA" else "Authorize INTERNAL_VALIDATION, including only six executable PARTIAL calculations?"
        if QMessageBox.question(self, "Confirm policy decision", confirmation) != QMessageBox.Yes: return
        try: authorize_activation_profile(self.database, request_id, selected, operator_id=self.operator_id, confirmed=True)
        except Exception as error: QMessageBox.critical(self, "Profile authorization failed", str(error)); return
        if QMessageBox.question(self, "Issue licence", "Issue a 90-day device-bound licence for this approved request?") != QMessageBox.Yes: return
        try:
            selected_profile = Profile(selected)
            app_id = self.database.connection.execute("SELECT application_id FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()[0]
            if self.test_mode:
                envelope, event_id = issue_for_request_for_testing(self.database, self.authority, request_id, operator_id=self.operator_id, confirmed=True)
            else:
                envelope, event_id = self.authority.issue(app_id, request_id, selected_profile, confirmed=True)
            QMessageBox.information(self, "Licence issued", f"Licence {envelope['licence_id']} issued. Select it in Licences and export it for controlled delivery.")
            self.refresh()
        except Exception as error: QMessageBox.critical(self, "Issuance failed", str(error))

    def export_selected(self):
        licence_id = self._selected_id(self.licences_table)
        if not licence_id: return
        row = self.database.connection.execute("SELECT envelope_json,audit_event_id FROM licences WHERE licence_id=?", (licence_id,)).fetchone()
        if not row: return
        directory = QFileDialog.getExistingDirectory(self, "Choose controlled delivery folder")
        if not directory: return
        try:
            export_licence(directory, json.loads(row[0]), row[1], database=self.database, operator_id=self.operator_id)
            QMessageBox.information(self, "Export complete", f"Licence {licence_id} and operator receipt were exported.")
            self.refresh()
        except Exception as error: QMessageBox.critical(self, "Export failed", str(error))

    def export_public_key(self):
        status = self.authority.status()
        if not status.available:
            QMessageBox.warning(self, "Signing authority unavailable", status.message)
            return
        try:
            record_public_metadata(self.database, self.authority, operator_id=self.operator_id)
            path, _ = QFileDialog.getSaveFileName(self, "Export licence public key metadata", "licence-public-key.json", "JSON (*.json)")
            if path:
                from .exports import _atomic
                _atomic(Path(path), json.dumps(public_key_record(self.authority), sort_keys=True, separators=(",", ":")).encode("utf-8"))
                with self.database.transaction() as db:
                    from .audit import append_event
                    append_event(db, "public_key_export", self.operator_id, [status.kid], {"purpose": "client_trust_configuration"})
        except Exception as error: QMessageBox.critical(self, "Public key export failed", str(error))

    def revoke_selected(self):
        licence_id = self._selected_id(self.licences_table)
        if not licence_id: return
        if QMessageBox.question(self, "Revoke licence", "Record administrative revocation? A delivered offline licence is not invalidated immediately.") != QMessageBox.Yes: return
        try: revoke_licence(self.database, licence_id, operator_id=self.operator_id, confirmed=True); self.refresh()
        except Exception as error: QMessageBox.warning(self, "Revocation failed", str(error))

    def verify_audit(self):
        result = verify_chain(self.database.connection)
        QMessageBox.information(self, "Audit chain", f"Valid: {result[0]} · events checked: {result[1]}" + (f" · first failure: {result[2]}" if result[2] else ""))
