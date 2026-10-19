"""Standalone operator UI for the private Licence Manager."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QHBoxLayout, QHeaderView,
    QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from .audit import append_event, current_operator_id, verify_chain
from .crypto import DataProtector
from .database import Database
from .exports import ExportRecoveryError, export_licence
from .imports import ImportRejected, import_activation_json, import_applicants_json
from .issuance import IssuanceRejected, authorize_activation_profile, issue_for_request_for_testing, record_expiries, revoke_licence, issue_website_activation_for_testing
from .models import Profile
from .paths import data_root
from .signing import AuthorityState, ProductionAuthority, SigningUnavailable, TestEphemeralAuthority, public_key_record, record_public_metadata
from .storage import StorageError, bootstrap_storage
from .website_sync import (
    WebsiteLicenceSyncError,
    sync_website_test_licence_metadata,
    WebsiteStatusSyncError,
    WebsiteSyncError,
    fetch_website_activations,
    sync_local_application_status,
    sync_website_applications,
)


PAGES = ("Overview", "Applications", "Activation Requests", "Licences", "Audit Log", "Settings")
_STATUS_COLORS = {
    "APPLIED": "#16607a", "UNDER_REVIEW": "#946200", "APPROVED": "#17623e",
    "REJECTED": "#a33030", "LICENCE_ISSUED": "#17623e", "EXPIRED": "#946200",
    "REVOKED": "#a33030", "Authorized": "#17623e", "Pending": "#946200", "Issued": "#17623e",
    "Active": "#17623e", "Expired": "#946200", "Revoked": "#a33030",
}


class LicenceManagerWindow(QMainWindow):
    def __init__(self, *, test_mode=False, database=None, authority=None, data_root_override=None):
        super().__init__()
        self.setWindowTitle("Quantum Studio Licence Manager")
        self.resize(1180, 760)
        self.test_mode = bool(test_mode)
        self.operator_id = current_operator_id()
        self._temporary = None
        self._owns_database = database is None
        if database is None:
            if self.test_mode and data_root_override is not None:
                database = bootstrap_storage(data_root_override)
            elif self.test_mode:
                self._temporary = tempfile.TemporaryDirectory(prefix="qs-lm-test-")
                protector = DataProtector.for_testing(os.urandom(32))
                root = data_root_override or self._temporary.name
            else:
                root = data_root(data_root_override)
                database = bootstrap_storage(root)
            if self.test_mode and database is None:
                database = Database(root, protector)
        self.database = database
        self.authority = authority or (TestEphemeralAuthority() if self.test_mode else ProductionAuthority(
            data_root(data_root_override) / "licence-signing-key.dpapi",
            data_root(data_root_override) / "licence-signing-public.json", database=database))
        self._website_activations = ()
        self._build_ui()
        self.refresh()

    def closeEvent(self, event):
        # Release SQLite before deleting disposable Windows TEST storage.
        # Injected databases belong to the caller and remain open.
        if self._owns_database:
            self.database.close()
            self._owns_database = False
            if self._temporary is not None:
                self._temporary.cleanup()
                self._temporary = None
        super().closeEvent(event)

    def _build_ui(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {background:#f5f8fb;color:#183247;font-family:'Segoe UI';font-size:10pt}
            QLabel#title {font-size:19pt;font-weight:600;color:#103c59}
            QLabel#pageTitle {font-size:15pt;font-weight:600;color:#103c59}
            QLabel#notice {padding:8px;border-radius:4px;background:#e5f2f7;color:#17475c}
            QListWidget, QTableWidget, QTextEdit, QLineEdit, QComboBox {
                background:white;border:1px solid #c8d8e1;border-radius:4px}
            QListWidget::item {padding:10px}
            QListWidget::item:selected {background:#dff2f7;color:#075d77}
            QPushButton {background:#087f9b;color:white;border:1px solid #087f9b;
                border-radius:4px;padding:7px 12px;min-height:20px}
            QPushButton:hover {background:#066b84}
            QPushButton:disabled {background:#d6e0e5;color:#52636b;border-color:#d6e0e5}
            QPushButton:focus, QListWidget:focus, QTableWidget:focus,
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border:2px solid #085eae}
            QHeaderView::section {background:#eaf1f5;color:#183247;padding:7px;
                border:0;border-bottom:1px solid #c8d8e1}
            QTableWidget::item:selected {background:#dff2f7;color:#183247}
        """)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 14, 16, 14)
        head = QHBoxLayout()
        mark = QSvgWidget(str(Path(__file__).resolve().parents[2] / "assets" / "quantum-studio-v0.1.svg"))
        mark.setFixedSize(40, 38)
        head.addWidget(mark)
        brand = QLabel("Quantum Studio")
        brand.setStyleSheet("font-size:15pt;font-weight:600;color:#087f9b")
        title = QLabel("Licence Manager")
        title.setObjectName("title")
        head.addWidget(brand)
        head.addStretch()
        head.addWidget(title)
        layout.addLayout(head)

        self.mode_banner = QLabel("TEST MODE — ephemeral signing only; files and licences are test data"
                                  if self.test_mode else "PRODUCTION MODE — operator workstation")
        self.mode_banner.setStyleSheet("background:#fff0c2;color:#704800;padding:8px;border-radius:4px;font-weight:600")
        layout.addWidget(self.mode_banner)
        self.authority_banner = QLabel()
        self.authority_banner.setWordWrap(True)
        layout.addWidget(self.authority_banner)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.nav = QListWidget()
        self.nav.setAccessibleName("Licence Manager sections")
        self.nav.addItems(PAGES)
        self.nav.setFixedWidth(205)
        self.pages = QStackedWidget()
        body.addWidget(self.nav)
        body.addWidget(self.pages, 1)
        layout.addLayout(body, 1)
        self.page_widgets = {}
        for name in PAGES:
            page = QWidget()
            box = QVBoxLayout(page)
            box.setSpacing(10)
            heading = QLabel(name)
            heading.setObjectName("pageTitle")
            box.addWidget(heading)
            if name == "Overview":
                self._build_overview(box)
            elif name == "Applications":
                self.applications_table = self._table(box, "Applications", ("Application ID", "Status", "Imported"))
                self.application_search, self.application_filter = self._filters(
                    box, self.applications_table, ("All statuses", "APPLIED", "UNDER_REVIEW", "APPROVED",
                                                   "REJECTED", "LICENCE_ISSUED", "EXPIRED", "REVOKED"), 1)
                self._actions(box, (("Sync website applications", self.sync_website_applications),
                                    ("Sync status to website", self.sync_selected_status_to_website),
                                    ("Import applications…", self.import_applicants),
                                    ("Review", lambda: self.transition_selected("UNDER_REVIEW")),
                                    ("Approve", lambda: self.transition_selected("APPROVED")),
                                    ("Reject…", lambda: self.transition_selected("REJECTED")),
                                    ("Show details", self.show_selected_details)))
                self.details = QTextEdit()
                self.details.setReadOnly(True)
                self.details.setAccessibleName("Selected applicant details; contains sensitive personal information")
                self.details.setPlaceholderText("Select an application, then choose Show details. Personal information is hidden until requested.")
                self.details.setMaximumHeight(170)
                box.addWidget(self.details)
            elif name == "Activation Requests":
                self.requests_table = self._table(box, "Activation requests",
                    ("Request ID", "Application ID", "Status", "Requested profile", "Application version", "Authorized profile"))
                self.request_search, self.request_filter = self._filters(
                    box, self.requests_table, ("All statuses", "Pending", "Authorized", "Issued"), 2)
                self._actions(box, (("Import request…", self.import_activation),
                                    ("Authorize and issue…", self.issue_selected)))
                self.website_activations_table = self._table(
                    box,
                    "Website beta activations",
                    ("Activation ID", "Application ID", "Installation", "Status", "Flag", "Platform", "Version", "Local licence", "Website licence", "TEST signer"),
                )
                actions = self._actions(box, (
                    ("Refresh website activations", self.refresh_website_activations),
                    ("Issue test licence", self.issue_selected_website_test_licence),
                    ("Sync licence metadata", self.sync_selected_website_test_licence_metadata),
                ))
                self.issue_website_test_licence_button = actions[1]
                self.sync_website_test_licence_button = actions[2]
                self.website_activations_table.itemSelectionChanged.connect(self._update_website_licence_actions)
                self._update_website_licence_actions()
            elif name == "Licences":
                self.licences_table = self._table(box, "Licences",
                    ("Licence ID", "Profile", "Issued", "Expires", "Status"))
                self.licence_search, self.licence_filter = self._filters(
                    box, self.licences_table, ("All statuses", "Active", "Expired", "Revoked"), 4)
                self._actions(box, (("Export…", self.export_selected), ("Revoke…", self.revoke_selected)))
            elif name == "Audit Log":
                self.audit_table = self._table(box, "Audit events", ("Timestamp", "Event", "Operator", "Hash"))
                self.audit_search, self.audit_filter = self._filters(box, self.audit_table, ("All events",), 1)
                self._actions(box, (("Verify audit chain", self.verify_audit),))
            else:
                self.settings = QTextEdit()
                self.settings.setReadOnly(True)
                self.settings.setAccessibleName("Signing authority and storage status")
                box.addWidget(self.settings)
                self._actions(box, (("Export signing public key…", self.export_public_key),))
            self.page_widgets[name] = page
            self.pages.addWidget(page)
        self.nav.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.nav.currentRowChanged.connect(lambda index: self.details.clear() if index != 1 else None)
        self.nav.setCurrentRow(0)
        self.applications_table.itemSelectionChanged.connect(self.details.clear)
        self._shortcuts = []
        for index in range(len(PAGES)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda index=index: self.nav.setCurrentRow(index))
            self._shortcuts.append(shortcut)
        self.feedback = QLabel("Ready")
        self.feedback.setObjectName("notice")
        self.feedback.setAccessibleName("Operation status")
        layout.addWidget(self.feedback)
        self.setCentralWidget(root)

    def _build_overview(self, box):
        self.dashboard = QTextEdit()
        self.dashboard.setReadOnly(True)
        self.dashboard.setAccessibleName("Licence Manager overview")
        box.addWidget(self.dashboard)
        self._actions(box, (("Review applications", lambda: self.nav.setCurrentRow(1)),
                            ("Review activation requests", lambda: self.nav.setCurrentRow(2)),
                            ("View licences", lambda: self.nav.setCurrentRow(3))))
        self.maintenance_note = QLabel("Refresh records licence expiries and signing-authority status in the audit log.")
        self.maintenance_note.setWordWrap(True)
        box.addWidget(self.maintenance_note)
        self._actions(box, (("Refresh and record maintenance", self.refresh),))

    @staticmethod
    def _actions(box, actions):
        row = QHBoxLayout()
        buttons = []
        for label, callback in actions:
            button = QPushButton(label)
            button.setAccessibleName(label)
            button.clicked.connect(callback)
            buttons.append(button)
            row.addWidget(button)
        row.addStretch()
        box.addLayout(row)
        return buttons

    @staticmethod
    def _table(box, label, headers):
        table = QTableWidget()
        table.setAccessibleName(label)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setDefaultSectionSize(160)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(True)
        box.addWidget(table, 1)
        table.empty_label = QLabel(f"No {label.lower()} to show.")
        table.empty_label.setAlignment(Qt.AlignCenter)
        box.addWidget(table.empty_label)
        return table

    @staticmethod
    def _filters(box, table, statuses, status_column):
        row = QHBoxLayout()
        search = QLineEdit()
        search.setPlaceholderText("Search visible identifiers and fields")
        search.setAccessibleName(f"Search {table.accessibleName().lower()}")
        status = QComboBox()
        status.addItems(statuses)
        status.setAccessibleName(f"Filter {table.accessibleName().lower()} by status")
        row.addWidget(search, 1)
        row.addWidget(status)
        box.addLayout(row)
        search.textChanged.connect(lambda: LicenceManagerWindow._apply_filter(table, search, status, status_column))
        status.currentIndexChanged.connect(lambda: LicenceManagerWindow._apply_filter(table, search, status, status_column))
        shortcut = QShortcut(QKeySequence("Ctrl+F"), search)
        shortcut.activated.connect(search.setFocus)
        return search, status

    @staticmethod
    def _apply_filter(table, search, status, status_column):
        needle = search.text().strip().casefold()
        chosen = status.currentText()
        for row in range(table.rowCount()):
            values = [table.item(row, col).text() if table.item(row, col) else "" for col in range(table.columnCount())]
            matches_text = not needle or any(needle in value.casefold() for value in values)
            matches_status = chosen.startswith("All ") or values[status_column] == chosen
            table.setRowHidden(row, not (matches_text and matches_status))

    @staticmethod
    def _fill(table, rows, headers, status_column=None):
        selected = table.item(table.currentRow(), 0) if table.currentRow() >= 0 else None
        selected_id = selected.text() if selected else None
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)
        table.setRowCount(len(rows))
        table.setHorizontalHeaderLabels(headers)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setToolTip(item.text())
                if status_column == c:
                    color = _STATUS_COLORS.get(item.text())
                    if color:
                        item.setForeground(QColor(color))
                table.setItem(r, c, item)
        table.setUpdatesEnabled(True)
        table.setSortingEnabled(True)
        table.empty_label.setVisible(not rows)
        if selected_id:
            for row in range(table.rowCount()):
                if table.item(row, 0).text() == selected_id:
                    table.selectRow(row)
                    break

    def _set_feedback(self, message, *, level="info"):
        colors = {"info": ("#e5f2f7", "#17475c"), "success": ("#e1f2e9", "#17623e"),
                  "warning": ("#fff0c2", "#704800"), "error": ("#ffe3e3", "#842525")}
        background, foreground = colors[level]
        self.feedback.setText(message)
        self.feedback.setStyleSheet(f"background:{background};color:{foreground};padding:8px;border-radius:4px")

    @staticmethod
    def _error_message(error, action):
        if isinstance(error, ImportRejected):
            return "The import was rejected. Check the file format, request age, and applicant status."
        if isinstance(error, IssuanceRejected):
            return "The request cannot be authorized or issued in its current state. Review the applicant and request."
        if isinstance(error, SigningUnavailable):
            return "The signing authority is unavailable. Review its status in Settings."
        if isinstance(error, ExportRecoveryError):
            return "Export needs operator review. Check the chosen destination before retrying."
        if isinstance(error, StorageError):
            return "Storage is unavailable. Preserve the existing data and request operator recovery."
        if isinstance(error, WebsiteStatusSyncError):
            return "Website status mirror is stale. The local decision is unchanged; retry when available."
        if isinstance(error, WebsiteLicenceSyncError):
            return str(error)
        if isinstance(error, WebsiteSyncError):
            return "Website sync could not be completed. Check the configured URL and authentication."
        return f"{action} could not be completed. No diagnostic or private data is shown here."

    def _show_error(self, title, error, action):
        message = self._error_message(error, action)
        self._set_feedback(message, level="error")
        QMessageBox.critical(self, title, message)

    def refresh(self):
        try:
            self._refresh_records()
        except Exception as error:
            self._set_feedback(self._error_message(error, "Refresh"), level="error")

    def _refresh_records(self):
        self._set_feedback("Refreshing and recording expiry and signing-authority maintenance…")
        db = self.database.connection
        record_expiries(self.database, operator_id=self.operator_id)
        status = self.authority.status()
        with self.database.transaction() as audit_db:
            append_event(audit_db, "signing_authority_status", self.operator_id, [], {"state": status.state.value, "mode": status.mode})
        applications = db.execute("SELECT application_id,status,imported_at FROM applicants ORDER BY imported_at DESC").fetchall()
        self._fill(self.applications_table, applications, ("Application ID", "Status", "Imported"), 1)
        requests = []
        for row in db.execute("""SELECT r.request_id,r.application_id,r.request_json,r.authorized_profile,
                               EXISTS(SELECT 1 FROM licences l WHERE l.request_id=r.request_id)
                               FROM activation_requests r ORDER BY r.imported_at DESC"""):
            request = json.loads(row[2])
            request_state = "Issued" if row[4] else "Authorized" if row[3] else "Pending"
            requests.append((row[0], row[1], request_state,
                             request.get("requested_profile", ""), request.get("application_version", ""), row[3] or ""))
        self._fill(self.requests_table, requests,
                   ("Request ID", "Application ID", "Status", "Requested profile", "Application version", "Authorized profile"), 2)
        now = int(datetime.now(timezone.utc).timestamp())
        licences = []
        for row in db.execute("SELECT licence_id,profile,issued_at,expires_at,revoked_at FROM licences ORDER BY issued_at DESC"):
            state = "Revoked" if row[4] else "Expired" if row[3] <= now else "Active"
            licences.append((row[0], row[1], self._date(row[2]), self._date(row[3]), state))
        self._fill(self.licences_table, licences, ("Licence ID", "Profile", "Issued", "Expires", "Status"), 4)
        events = db.execute("SELECT timestamp,event_type,operator_id,event_hash FROM audit_events ORDER BY seq DESC").fetchall()
        self._fill(self.audit_table, events, ("Timestamp", "Event", "Operator", "Hash"))
        selected_event = self.audit_filter.currentText()
        self.audit_filter.blockSignals(True)
        self.audit_filter.clear()
        self.audit_filter.addItems(("All events", *sorted({row[1] for row in events})))
        if selected_event in {self.audit_filter.itemText(i) for i in range(self.audit_filter.count())}:
            self.audit_filter.setCurrentText(selected_event)
        self.audit_filter.blockSignals(False)
        for table, search, filter_box, column in (
            (self.applications_table, self.application_search, self.application_filter, 1),
            (self.requests_table, self.request_search, self.request_filter, 2),
            (self.licences_table, self.licence_search, self.licence_filter, 4),
            (self.audit_table, self.audit_search, self.audit_filter, 1),
        ):
            self._apply_filter(table, search, filter_box, column)
        awaiting = db.execute("SELECT COUNT(*) FROM applicants WHERE status IN ('APPLIED','UNDER_REVIEW')").fetchone()[0]
        awaiting_activation = db.execute("SELECT COUNT(*) FROM applicants a WHERE a.status='APPROVED' AND NOT EXISTS (SELECT 1 FROM activation_requests r WHERE r.application_id=a.application_id)").fetchone()[0]
        expiring = db.execute("SELECT COUNT(*) FROM licences WHERE revoked_at IS NULL AND expires_at BETWEEN ? AND ?", (now, now + 30 * 86400)).fetchone()[0]
        expired = db.execute("SELECT COUNT(*) FROM licences WHERE revoked_at IS NULL AND expires_at<=?", (now,)).fetchone()[0]
        revoked = db.execute("SELECT COUNT(*) FROM licences WHERE revoked_at IS NOT NULL").fetchone()[0]
        unavailable = status.state in {AuthorityState.UNINITIALIZED, AuthorityState.METADATA_INVALID, AuthorityState.PROTECTED_KEY_MISSING}
        self.authority_banner.setText(status.message)
        self.authority_banner.setStyleSheet(
            "background:#ffe3e3;color:#842525;padding:8px;border-radius:4px;font-weight:600"
            if unavailable else "background:#fff0c2;color:#704800;padding:8px;border-radius:4px;font-weight:600")
        self.dashboard.setPlainText(
            f"Applications awaiting review: {awaiting}\n"
            f"Approved applicants awaiting activation: {awaiting_activation}\n"
            f"Pending activation requests: {sum(request[2] == 'Pending' for request in requests)}\n"
            f"Licences expiring within 30 days: {expiring}\n"
            f"Expired licences: {expired}\n"
            f"Revoked licences: {revoked}\n\nSigning authority: {status.message}")
        history = f"\nHistorical last authorized use: {status.last_authorized_use_at}" if status.last_authorized_use_at else ""
        self.settings.setPlainText(
            f"Storage: database connected; verify the audit chain separately\nMode: {status.mode}\nState: {status.state.value}\nStatus: {status.message}{history}\n"
            f"Key ID: {status.kid or '—'}\nPublic-key fingerprint: {status.public_key_fingerprint or '—'}\n\n"
            "Production key initialization is intentionally unavailable in this release.\n"
            "Licence trust is separate from updater signing.")
        self._set_feedback("Lists updated. Licence expiries and signing-authority status were recorded in the audit log.", level="success")

    @staticmethod
    def _date(value):
        return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def _refresh_tables(self):
        self.refresh()

    @staticmethod
    def _selected_id(table):
        row = table.currentRow()
        if row >= 0 and table.isRowHidden(row):
            return None
        item = table.item(row, 0) if row >= 0 else None
        return item.text() if item else None

    def import_applicants(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import version 1 website application export", "", "JSON (*.json)")
        if not path:
            return
        try:
            count = import_applicants_json(Path(path), self.database, operator_id=self.operator_id)
            self.refresh()
            message = f"Imported {count} new application(s)."
            self._set_feedback(message, level="success")
            QMessageBox.information(self, "Import complete", message)
        except Exception as error:
            self._show_error("Import failed", error, "Import")

    def sync_website_applications(self):
        try:
            result = sync_website_applications(
                self.database,
                operator_id=self.operator_id,
                test_mode=self.test_mode,
            )
            self.refresh()
            message = (
                f"Fetched: {result.fetched}\n"
                f"Imported: {result.imported}\n"
                f"Duplicates: {result.duplicates}\n"
                f"Rejected: {result.rejected}"
            )
            self._set_feedback(
                message,
                level="warning" if result.rejected else "success",
            )
        except Exception as error:
            self._show_error("Website sync failed", error, "Website sync")

    def sync_selected_status_to_website(self):
        application_id = self._selected_id(self.applications_table)
        if not application_id:
            self._set_feedback("Select an application first.", level="warning")
            return
        try:
            result = sync_local_application_status(
                self.database,
                application_id,
                test_mode=self.test_mode,
            )
            state = (
                "already current"
                if result.result == "already_current"
                else "updated"
            )
            self._set_feedback(
                f"Website status mirror {state}: {result.status}.",
                level="success",
            )
        except Exception as error:
            self._show_error("Website status sync failed", error, "Website status sync")

    def refresh_website_activations(self):
        try:
            self._website_activations = fetch_website_activations(test_mode=self.test_mode)
            self._render_website_activations()
            self._set_feedback(
                f"Loaded {len(self._website_activations)} website activation record(s). Website facts are read-only; TEST issuance is local.",
                level="success")
        except Exception as error:
            self._show_error("Website activations unavailable", error, "Website activation refresh")

    def _selected_website_activation(self):
        selected = self._selected_id(self.website_activations_table)
        return next((item for item in self._website_activations if item.activation_request_id == selected), None)

    def _local_website_licence(self, activation):
        if activation is None:
            return None
        return self.database.connection.execute(
            "SELECT licence_id,envelope_json FROM website_activation_licences WHERE activation_request_id=?",
            (activation.activation_request_id,)).fetchone()

    def _render_website_activations(self):
        selected = self._selected_id(self.website_activations_table)
        rows = []
        for activation in self._website_activations:
            local = self._local_website_licence(activation)
            signer = ""
            if local:
                signer = ("Current TEST key" if json.loads(local["envelope_json"])["kid"] == self.authority.status().kid
                          else "Prior TEST key; not re-signed")
            rows.append((activation.activation_request_id, activation.application_id,
                         activation.installation_id, activation.status, activation.flag_reason or "",
                         activation.platform, activation.app_version, local["licence_id"] if local else "",
                         activation.licence_id or "", signer))
        self._fill(self.website_activations_table, rows,
                   ("Activation ID", "Application ID", "Installation", "Status", "Flag", "Platform", "Version", "Local licence", "Website licence", "TEST signer"), 3)
        for row in range(self.website_activations_table.rowCount()):
            if self.website_activations_table.item(row, 0).text() == selected:
                self.website_activations_table.selectRow(row)
        self._update_website_licence_actions()

    def _update_website_licence_actions(self):
        activation = self._selected_website_activation()
        local = self._local_website_licence(activation)
        eligible = bool(self.test_mode and activation and activation.status == "AUTHORIZED")
        self.issue_website_test_licence_button.setEnabled(bool(
            eligible and activation.device_public_key_hash and not local and not activation.licence_id))
        self.sync_website_test_licence_button.setEnabled(bool(eligible and local))

    def issue_selected_website_test_licence(self):
        activation = self._selected_website_activation()
        if not self.test_mode or not activation or activation.status != "AUTHORIZED":
            self._set_feedback("Select an AUTHORIZED website activation in TEST MODE.", level="warning")
            return
        try:
            if activation.licence_id and not self._local_website_licence(activation):
                raise WebsiteLicenceSyncError("The website already has a licence; recover its local database before issuing.")
            envelope = issue_website_activation_for_testing(
                self.database, self.authority, activation, operator_id=self.operator_id)
            self._render_website_activations()
            self._set_feedback(f"TEST licence {envelope['licence_id']} stored locally. Sync licence metadata separately. TEST keys are ephemeral; an existing licence is never re-signed.", level="success")
        except Exception as error:
            self._show_error("TEST licence issuance failed", error, "TEST licence issuance")

    def sync_selected_website_test_licence_metadata(self):
        activation = self._selected_website_activation()
        local = self._local_website_licence(activation)
        if not self.test_mode or activation is None or local is None:
            self._set_feedback("Select a website activation with a stored TEST licence.", level="warning")
            return
        try:
            result = sync_website_test_licence_metadata(
                activation, json.loads(local["envelope_json"]), test_mode=self.test_mode)
            self._set_feedback(f"Website licence metadata {result}: {local['licence_id']}.", level="success")
        except Exception as error:
            self._show_error("Licence metadata sync failed", error, "Licence metadata sync")

    def import_activation(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Quantum Studio activation request", "", "JSON (*.json)")
        if not path:
            return
        try:
            imported = import_activation_json(Path(path), self.database, operator_id=self.operator_id)
            self.refresh()
            message = "Request imported." if imported else "Identical request was already imported."
            self._set_feedback(message, level="success")
            QMessageBox.information(self, "Activation request", message)
        except Exception as error:
            self._show_error("Import failed", error, "Import")

    def transition_selected(self, state):
        app_id = self._selected_id(self.applications_table)
        if not app_id:
            self._set_feedback("Select an application first.", level="warning")
            return
        prompt = {"APPROVED": "Approve this application? This decision is audited.",
                  "REJECTED": "Reject this application? This decision is audited."}.get(state)
        if prompt and QMessageBox.question(self, "Confirm application decision", prompt) != QMessageBox.Yes:
            return
        try:
            from .models import ApplicantStatus
            self.database.transition(app_id, ApplicantStatus(state), operator_id=self.operator_id,
                                     note_code="rejected_by_operator" if state == "REJECTED"
                                     else "approved_by_operator" if state == "APPROVED" else "manual_review")
            self.details.clear()
            self.refresh()
            self._set_feedback("Application status updated and audited.", level="success")
        except Exception as error:
            self._show_error("Application was not changed", error, "Application update")

    def show_selected_details(self):
        app_id = self._selected_id(self.applications_table)
        if not app_id:
            self._set_feedback("Select an application first.", level="warning")
            return
        try:
            self.details.setPlainText(json.dumps(self.database.applicant_pii(app_id), indent=2, ensure_ascii=False))
            self.details.setFocus()
            self._set_feedback("Sensitive applicant details are visible in the details pane.", level="warning")
        except Exception as error:
            self.details.clear()
            self._show_error("Details unavailable", error, "Applicant details")

    def issue_selected(self):
        request_id = self._selected_id(self.requests_table)
        if not request_id:
            QMessageBox.information(self, "Issue licence", "Select an activation request first.")
            return
        profiles = ["PROFESSOR_BETA", "INTERNAL_VALIDATION"]
        selected, ok = QInputDialog.getItem(self, "Authorize entitlement profile", "Select the local operator-approved profile:", profiles, 0, False)
        if not ok:
            return
        confirmation = ("Authorize the 90-day PROFESSOR_BETA profile?" if selected == "PROFESSOR_BETA"
                        else "Authorize INTERNAL_VALIDATION, including only six executable PARTIAL calculations?")
        if QMessageBox.question(self, "Confirm policy decision", confirmation) != QMessageBox.Yes:
            return
        try:
            authorize_activation_profile(self.database, request_id, selected, operator_id=self.operator_id, confirmed=True)
        except Exception as error:
            self._show_error("Profile authorization failed", error, "Profile authorization")
            return
        if QMessageBox.question(self, "Issue licence", "Issue a 90-day device-bound licence for this approved request?") != QMessageBox.Yes:
            self.refresh()
            self._set_feedback("Profile authorization was recorded; licence issuance was cancelled.", level="warning")
            return
        try:
            profile = Profile(selected)
            row = self.database.connection.execute(
                "SELECT application_id FROM activation_requests WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise IssuanceRejected("Request missing")
            if self.test_mode:
                envelope, _ = issue_for_request_for_testing(
                    self.database, self.authority, request_id, operator_id=self.operator_id, confirmed=True)
            else:
                envelope, _ = self.authority.issue(row[0], request_id, profile, confirmed=True)
            self.refresh()
            self.nav.setCurrentRow(3)
            message = f"Licence {envelope['licence_id']} issued. Select it here to export it for controlled delivery."
            self._set_feedback(message, level="success")
            QMessageBox.information(self, "Licence issued", message)
        except Exception as error:
            self._show_error("Issuance failed", error, "Issuance")

    def export_selected(self):
        licence_id = self._selected_id(self.licences_table)
        if not licence_id:
            self._set_feedback("Select a licence first.", level="warning")
            return
        try:
            row = self.database.connection.execute(
                "SELECT envelope_json,audit_event_id FROM licences WHERE licence_id=?", (licence_id,)).fetchone()
            if not row:
                self._set_feedback("The selected licence is no longer available.", level="warning")
                return
            directory = QFileDialog.getExistingDirectory(self, "Choose controlled delivery folder")
            if not directory:
                return
            if QMessageBox.question(self, "Confirm licence export",
                                    "Export the selected licence and operator receipt to the chosen folder for controlled delivery?") != QMessageBox.Yes:
                return
            export_licence(directory, json.loads(row[0]), row[1], database=self.database, operator_id=self.operator_id)
            self.refresh()
            message = f"Licence {licence_id} and operator receipt were exported."
            self._set_feedback(message, level="success")
            QMessageBox.information(self, "Export complete", message)
        except Exception as error:
            self._show_error("Export failed", error, "Export")

    def export_public_key(self):
        try:
            status = self.authority.status()
            if not status.kid or status.public_key is None or status.state in {
                    AuthorityState.UNINITIALIZED, AuthorityState.METADATA_INVALID, AuthorityState.PROTECTED_KEY_MISSING}:
                self._set_feedback("Signing authority is unavailable. Review its status in Settings.", level="warning")
                QMessageBox.warning(self, "Signing authority unavailable", "Signing authority is unavailable. Review its status in Settings.")
                return
            record_public_metadata(self.database, self.authority, operator_id=self.operator_id)
            path, _ = QFileDialog.getSaveFileName(
                self, "Export licence public key metadata", "licence-public-key.json", "JSON (*.json)")
            if not path:
                return
            if QMessageBox.question(self, "Confirm public-key export",
                                    "Export public signing metadata to the chosen file?") != QMessageBox.Yes:
                return
            from .exports import _atomic
            _atomic(Path(path), json.dumps(public_key_record(self.authority), sort_keys=True, separators=(",", ":")).encode("utf-8"))
            with self.database.transaction() as db:
                append_event(db, "public_key_export", self.operator_id, [status.kid], {"purpose": "client_trust_configuration"})
            self._set_feedback("Public signing metadata was exported and audited.", level="success")
        except Exception as error:
            self._show_error("Public key export failed", error, "Public-key export")

    def revoke_selected(self):
        licence_id = self._selected_id(self.licences_table)
        if not licence_id:
            self._set_feedback("Select a licence first.", level="warning")
            return
        if QMessageBox.question(self, "Revoke licence",
                                "Record administrative revocation? A delivered offline licence is not invalidated immediately.") != QMessageBox.Yes:
            return
        try:
            revoke_licence(self.database, licence_id, operator_id=self.operator_id, confirmed=True)
            self.refresh()
            self._set_feedback("Licence revocation recorded and audited. Offline copies may remain usable.", level="warning")
        except Exception as error:
            self._show_error("Revocation failed", error, "Revocation")

    def verify_audit(self):
        try:
            valid, count, first_failure = verify_chain(self.database.connection)
            if valid:
                message = f"Audit chain valid. {count} event(s) checked."
                self._set_feedback(message, level="success")
                QMessageBox.information(self, "Audit chain", message)
            else:
                message = "Audit-chain verification failed. Preserve storage and request operator review."
                self._set_feedback(message, level="error")
                QMessageBox.warning(self, "Audit chain", message)
        except Exception as error:
            self._show_error("Audit verification failed", error, "Audit verification")
