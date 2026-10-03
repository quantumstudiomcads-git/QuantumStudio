from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import uuid
from unittest.mock import patch

from operator_tools.licence_manager.crypto import DataProtector
from operator_tools.licence_manager.crypto import WrongPurposeDataKeyError as CryptoWrongPurposeDataKeyError
from operator_tools.licence_manager.database import Database
from operator_tools.licence_manager import storage
from operator_tools.licence_manager.storage import (CorruptStorageError, InconsistentStorageError,
    InvalidPendingMarkerError, MissingDataKeyError, KeyPublicationConflictError,
    InitializationInProgressError, bootstrap_storage)


def _hold_storage_lock(root, ready, release):
    with storage._initialization_lock(Path(root), timeout=5.0):
        ready.set()
        release.wait(5.0)


class StorageBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qs-lm-storage-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "operator-data"
        self.generation_count = 0

        def initialize(cls, path, *, storage_generation_id):
            self.generation_count += 1
            target = Path(path)
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(json.dumps({"fixture_generation": storage_generation_id}).encode())
                stream.flush(); os.fsync(stream.fileno())
            return DataProtector.for_testing(b"P" * 32, storage_generation_id=storage_generation_id)

        def open_existing(cls, path):
            marker = json.loads(Path(path).read_text(encoding="utf-8"))
            return DataProtector.for_testing(b"P" * 32, storage_generation_id=marker["fixture_generation"])

        self.patches = [
            patch.object(DataProtector, "_initialize_new_windows_keyfile", classmethod(initialize)),
            patch.object(DataProtector, "open_existing_windows_keyfile", classmethod(open_existing)),
        ]
        for item in self.patches: item.start()
        self.addCleanup(lambda: [item.stop() for item in reversed(self.patches)])

    def test_first_run_initializes_one_matching_pair(self):
        database = bootstrap_storage(self.root)
        self.addCleanup(database.close)
        self.assertTrue(database.path.is_file())
        self.assertTrue((self.root / "data-key.dpapi").is_file())
        self.assertFalse((self.root / ".storage-initialization.pending").exists())
        self.assertEqual(self.generation_count, 1)
        stored = database.connection.execute("SELECT value FROM storage_metadata WHERE name='storage_generation_id'").fetchone()[0]
        self.assertEqual(stored, database.protector.storage_generation_id)
        second = bootstrap_storage(self.root)
        self.addCleanup(second.close)
        self.assertEqual(second.protector.storage_generation_id, stored)
        self.assertEqual(self.generation_count, 1)

    def test_database_without_key_fails_without_modifying_database(self):
        self.root.mkdir(parents=True)
        path = self.root / "operator.sqlite3"
        path.write_bytes(b"synthetic existing database bytes")
        before = path.read_bytes()
        with self.assertRaises(MissingDataKeyError): bootstrap_storage(self.root)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / "data-key.dpapi").exists())
        self.assertEqual(self.generation_count, 0)

    def test_zero_length_database_missing_key_fails_closed(self):
        self.root.mkdir(parents=True)
        (self.root / "operator.sqlite3").write_bytes(b"")
        with self.assertRaises(MissingDataKeyError): bootstrap_storage(self.root)
        self.assertFalse((self.root / "data-key.dpapi").exists())

    def test_key_without_database_requires_pending_initialization(self):
        self.root.mkdir(parents=True)
        generation = str(uuid.uuid4())
        (self.root / "data-key.dpapi").write_text(json.dumps({"fixture_generation": generation}))
        with self.assertRaises(InconsistentStorageError): bootstrap_storage(self.root)
        self.assertFalse((self.root / "operator.sqlite3").exists())

    def test_pair_generation_mismatch_fails_closed(self):
        database = bootstrap_storage(self.root)
        database.close()
        key = self.root / "data-key.dpapi"
        key.write_text(json.dumps({"fixture_generation": str(uuid.uuid4())}))
        with self.assertRaises(CorruptStorageError): bootstrap_storage(self.root)

    def test_pending_initialization_resumes_after_key_publication(self):
        calls = 0
        real_database = storage.Database
        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected migration interruption")
            return real_database(*args, **kwargs)
        with patch.object(storage, "Database", side_effect=fail_once):
            with self.assertRaises(CorruptStorageError): bootstrap_storage(self.root)
        first_generation = json.loads((self.root / "data-key.dpapi").read_text())["fixture_generation"]
        self.assertTrue((self.root / ".storage-initialization.pending").exists())
        database = bootstrap_storage(self.root)
        self.addCleanup(database.close)
        self.assertEqual(database.protector.storage_generation_id, first_generation)
        self.assertEqual(self.generation_count, 1)
        self.assertFalse((self.root / ".storage-initialization.pending").exists())

    def test_valid_pending_marker_and_existing_key_resume_without_generation(self):
        self.root.mkdir(parents=True)
        marker = self.root / ".storage-initialization.pending"
        generation = str(uuid.uuid4())
        storage._create_pending(marker, self.root, generation)
        DataProtector._initialize_new_windows_keyfile(self.root / "data-key.dpapi", storage_generation_id=generation)
        key_before = (self.root / "data-key.dpapi").read_bytes()
        database = bootstrap_storage(self.root)
        self.addCleanup(database.close)
        self.assertEqual(database.protector.storage_generation_id, generation)
        self.assertEqual((self.root / "data-key.dpapi").read_bytes(), key_before)
        self.assertEqual(self.generation_count, 1)
        self.assertFalse(marker.exists())

    def test_interruption_before_key_publication_resumes_same_pending_generation(self):
        calls = 0
        initializer = DataProtector._initialize_new_windows_keyfile.__func__
        def fail_before_publish(cls, path, *, storage_generation_id):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("injected pre-publication interruption")
            return initializer(cls, path, storage_generation_id=storage_generation_id)
        with patch.object(DataProtector, "_initialize_new_windows_keyfile", classmethod(fail_before_publish)):
            with self.assertRaises(CorruptStorageError): bootstrap_storage(self.root)
            marker_generation = storage._read_pending(self.root / ".storage-initialization.pending", self.root)
            database = bootstrap_storage(self.root)
        self.addCleanup(database.close)
        self.assertEqual(database.protector.storage_generation_id, marker_generation)
        self.assertEqual(calls, 2)
        self.assertFalse((self.root / ".storage-initialization.pending").exists())

    def test_completed_pair_with_pending_marker_finishes_marker_cleanup(self):
        with patch.object(storage, "_remove_pending", side_effect=OSError("injected cleanup interruption")):
            with self.assertRaises(storage.IncompleteInitializationError): bootstrap_storage(self.root)
        key_before = (self.root / "data-key.dpapi").read_bytes()
        db = bootstrap_storage(self.root)
        self.addCleanup(db.close)
        self.assertEqual((self.root / "data-key.dpapi").read_bytes(), key_before)
        self.assertFalse((self.root / ".storage-initialization.pending").exists())

    def test_missing_pair_metadata_fails_closed(self):
        database = bootstrap_storage(self.root)
        database.close()
        connection = sqlite3.connect(self.root / "operator.sqlite3")
        connection.execute("DELETE FROM storage_metadata WHERE name='storage_generation_id'")
        connection.commit()
        connection.close()
        with self.assertRaises(CorruptStorageError): bootstrap_storage(self.root)
        self.assertEqual(self.generation_count, 1)

    def test_malformed_pending_marker_fails_without_replacing_key(self):
        self.root.mkdir(parents=True)
        marker = self.root / ".storage-initialization.pending"
        marker.write_text("{}", encoding="ascii")
        with self.assertRaises(InvalidPendingMarkerError): bootstrap_storage(self.root)
        self.assertFalse((self.root / "data-key.dpapi").exists())
        self.assertFalse((self.root / "operator.sqlite3").exists())

    def test_pending_marker_is_bound_to_storage_root(self):
        other = Path(self.temp.name) / "other-root"
        self.root.mkdir(parents=True)
        marker = self.root / ".storage-initialization.pending"
        storage._create_pending(marker, self.root, str(uuid.uuid4()))
        other.mkdir()
        (other / marker.name).write_bytes(marker.read_bytes())
        with self.assertRaises(InvalidPendingMarkerError): bootstrap_storage(other)
        self.assertFalse((other / "data-key.dpapi").exists())
        self.assertFalse((other / "operator.sqlite3").exists())

    def test_existing_corrupt_database_is_preserved(self):
        database = bootstrap_storage(self.root)
        database.close()
        path = self.root / "operator.sqlite3"
        path.write_bytes(b"synthetic malformed sqlite database")
        before = path.read_bytes()
        with self.assertRaises(CorruptStorageError): bootstrap_storage(self.root)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.generation_count, 1)

    def test_corrupt_key_is_not_replaced(self):
        self.root.mkdir(parents=True)
        db = Database(self.root, DataProtector.for_testing(b"P" * 32))
        db.close()
        key_path = self.root / "data-key.dpapi"
        key_path.write_bytes(b"synthetic corrupt key")
        before = key_path.read_bytes()
        with self.assertRaises(CorruptStorageError): bootstrap_storage(self.root)
        self.assertEqual(key_path.read_bytes(), before)
        self.assertEqual(self.generation_count, 0)

    def test_wrong_purpose_key_is_not_replaced(self):
        self.root.mkdir(parents=True)
        db = Database(self.root, DataProtector.for_testing(b"P" * 32))
        db.close()
        key_path = self.root / "data-key.dpapi"
        key_path.write_bytes(b"synthetic protected envelope")
        before = key_path.read_bytes()
        def wrong_purpose(cls, path):
            raise CryptoWrongPurposeDataKeyError("synthetic wrong purpose")
        with patch.object(DataProtector, "open_existing_windows_keyfile", classmethod(wrong_purpose)):
            with self.assertRaises(storage.WrongPurposeDataKeyError): bootstrap_storage(self.root)
        self.assertEqual(key_path.read_bytes(), before)
        self.assertEqual(self.generation_count, 0)

    def test_wrong_storage_generation_fails_without_writes(self):
        database = bootstrap_storage(self.root)
        database.close()
        key_path = self.root / "data-key.dpapi"
        original = json.loads(key_path.read_text())
        original["fixture_generation"] = str(uuid.uuid4())
        key_path.write_text(json.dumps(original), encoding="utf-8")
        before = key_path.read_bytes()
        with self.assertRaises(CorruptStorageError): bootstrap_storage(self.root)
        self.assertEqual(key_path.read_bytes(), before)
        self.assertEqual(self.generation_count, 1)

    def test_stale_marker_does_not_authorize_missing_key(self):
        self.root.mkdir(parents=True)
        db_path = self.root / "operator.sqlite3"
        db_path.write_bytes(b"existing bytes")
        marker = self.root / ".storage-initialization.pending"
        storage._create_pending(marker, self.root, str(uuid.uuid4()))
        with self.assertRaises(MissingDataKeyError): bootstrap_storage(self.root)
        self.assertFalse((self.root / "data-key.dpapi").exists())
        self.assertEqual(db_path.read_bytes(), b"existing bytes")

    def test_lock_failure_never_falls_back_to_initialization(self):
        from contextlib import contextmanager
        @contextmanager
        def fail_lock(_root):
            raise InitializationInProgressError("busy")
            yield
        with patch.object(storage, "_initialization_lock", fail_lock):
            with self.assertRaises(InitializationInProgressError): bootstrap_storage(self.root)
        self.assertFalse((self.root / "data-key.dpapi").exists())
        self.assertFalse((self.root / "operator.sqlite3").exists())
        self.assertEqual(self.generation_count, 0)

    @unittest.skipUnless(os.name == "nt", "Windows file-lock process test")
    def test_cross_process_lock_timeout_prevents_initialization(self):
        self.root.mkdir(parents=True)
        context = multiprocessing.get_context("spawn")
        ready = context.Event()
        release = context.Event()
        process = context.Process(target=_hold_storage_lock, args=(str(self.root), ready, release))
        process.start()
        self.addCleanup(lambda: (release.set(), process.join(5.0), process.is_alive() and process.terminate()))
        self.assertTrue(ready.wait(5.0))
        with patch.object(storage, "_LOCK_TIMEOUT_SECONDS", 0.05):
            try:
                unexpected = bootstrap_storage(self.root)
            except InitializationInProgressError:
                pass
            else:
                unexpected.close()
                self.fail("cross-process lock was not enforced")
        self.assertFalse((self.root / "data-key.dpapi").exists())
        self.assertFalse((self.root / "operator.sqlite3").exists())
        self.assertEqual(self.generation_count, 0)

    def test_key_publish_conflict_does_not_overwrite(self):
        def conflict(cls, path, *, storage_generation_id):
            Path(path).write_bytes(b"racing synthetic key")
            raise FileExistsError
        with patch.object(DataProtector, "_initialize_new_windows_keyfile", classmethod(conflict)):
            with self.assertRaises(KeyPublicationConflictError): bootstrap_storage(self.root)
        self.assertEqual((self.root / "data-key.dpapi").read_bytes(), b"racing synthetic key")
        self.assertFalse((self.root / "operator.sqlite3").exists())
        self.assertEqual(self.generation_count, 0)

    def test_concurrent_first_run_creates_one_key_and_pair(self):
        barrier = threading.Barrier(2)
        outcomes = []
        def open_storage():
            barrier.wait()
            db = bootstrap_storage(self.root)
            outcomes.append(db.protector.storage_generation_id)
            db.close()
        threads = [threading.Thread(target=open_storage) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=15)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(self.generation_count, 1)

    def test_symlink_key_is_rejected(self):
        self.root.mkdir(parents=True)
        target = self.root / "elsewhere"
        target.write_text("fixture")
        link = self.root / "data-key.dpapi"
        try: link.symlink_to(target)
        except (OSError, NotImplementedError): self.skipTest("Symlink creation unavailable")
        with self.assertRaises(storage.UnsafeStorageError): bootstrap_storage(self.root)

    def test_symlink_database_is_rejected(self):
        self.root.mkdir(parents=True)
        target = self.root / "elsewhere"
        target.write_bytes(b"synthetic")
        link = self.root / "operator.sqlite3"
        try: link.symlink_to(target)
        except (OSError, NotImplementedError): self.skipTest("Symlink creation unavailable")
        with self.assertRaises(storage.UnsafeStorageError): bootstrap_storage(self.root)
        self.assertFalse((self.root / "data-key.dpapi").exists())

    def test_offscreen_application_blocks_missing_key_without_replacement(self):
        from PySide6.QtWidgets import QApplication, QMessageBox
        from operator_tools.licence_manager import app as manager_app
        qt_app = QApplication.instance() or QApplication([])
        local_appdata = Path(self.temp.name) / "synthetic-local-appdata"
        root = local_appdata / "QuantumStudio" / "LicenceManager"
        root.mkdir(parents=True)
        database_path = root / "operator.sqlite3"
        database_path.write_bytes(b"synthetic existing database bytes")
        before = database_path.read_bytes()
        shown = []
        with patch.dict(os.environ, {"LOCALAPPDATA": str(local_appdata)}), \
             patch.object(QMessageBox, "critical", side_effect=lambda *args: shown.append(args[2])), \
             patch.object(manager_app.sys, "argv", ["licence-manager"]):
            code = manager_app.main([])
        self.assertEqual(code, 2)
        self.assertEqual(len(shown), 1)
        self.assertIn("protected data key is missing", shown[0])
        self.assertIn("existing database has been preserved", shown[0])
        self.assertEqual(database_path.read_bytes(), before)
        self.assertFalse((root / "data-key.dpapi").exists())
        self.assertFalse((root / "licence-signing-key.dpapi").exists())
        self.assertFalse((root / "licence-signing-public.json").exists())
        self.assertIsNotNone(qt_app)


if __name__ == "__main__":
    unittest.main()
