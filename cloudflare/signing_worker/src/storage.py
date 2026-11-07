"""Cloudflare SQL adapter. No sqlite3, file storage, private keys, or HTTP here."""
from dataclasses import dataclass
import secrets

from operator_tools.licence_manager.signing_service_auth import RequestRejected, FRESHNESS_SECONDS

LEASE_SECONDS = 60


class Row(dict):
    def __getitem__(self, key):
        return tuple(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, rows, written):
        self._rows = iter(rows)
        self.rowcount = written
    def fetchone(self): return next(self._rows, None)
    def __iter__(self): return self._rows


class DurableSql:
    """A small DB-API-shaped facade over ctx.storage.sql, used by shared issuance."""
    def __init__(self, storage): self.storage = storage
    def execute(self, statement, parameters=()):
        from js import Uint8Array
        from pyodide.ffi import to_js
        bindings = [Uint8Array.new(to_js(list(value))).buffer if isinstance(value, bytes) else value for value in parameters]
        cursor = self.storage.sql.exec(statement, *bindings)
        columns = cursor.columnNames
        names = list(columns.to_py() if hasattr(columns,"to_py") else columns)
        rows = []
        raw = cursor.raw().toArray()
        records = raw.to_py() if hasattr(raw,"to_py") else raw
        for record in records:
            values = []
            for value in record:
                # Public verification keys are the only BLOBs passed to the database.
                if hasattr(value, 'byteLength'):
                    value = bytes(Uint8Array.new(value).to_py())
                elif isinstance(value, memoryview): value = value.tobytes()
                values.append(value)
            rows.append(Row(zip(names, values)))
        return Cursor(rows, int(cursor.rowsWritten))

    def transaction(self, action):
        from pyodide.ffi import create_proxy
        # Do not return Python objects across the JS callback boundary.
        result = []
        failures = []
        def run():
            try: result.append(action(self))
            except BaseException as error:
                failures.append(error)
                raise
        proxy = create_proxy(run)
        try:
            self.storage.transactionSync(proxy)
        except BaseException:
            if failures: raise failures[0] from None
            raise
        finally: proxy.destroy()
        return result[0]


@dataclass(frozen=True)
class Lease:
    owner: str
    fence: int


class DurableJournal:
    def __init__(self, sql, environment, identity):
        self.sql, self.environment = sql, environment
        self.storage_identity = identity + ':journal'
        def initialize(db):
            db.execute('CREATE TABLE IF NOT EXISTS service_metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS request_nonces(caller TEXT,nonce TEXT,expires_at INTEGER,PRIMARY KEY(caller,nonce))')
            db.execute('CREATE INDEX IF NOT EXISTS nonce_expiry ON request_nonces(expires_at)')
            db.execute('CREATE TABLE IF NOT EXISTS issuance_lease(singleton INTEGER PRIMARY KEY CHECK(singleton=1),owner TEXT,expires_at INTEGER,fence INTEGER NOT NULL)')
            row = db.execute("SELECT value FROM service_metadata WHERE name='environment'").fetchone()
            if row and row[0] != environment.value: raise RequestRejected(503,'configuration_unavailable')
            db.execute("INSERT OR IGNORE INTO service_metadata VALUES('environment',?)",(environment.value,))
            db.execute('INSERT OR IGNORE INTO issuance_lease VALUES(1,NULL,0,0)')
        sql.transaction(initialize)

    def _clock(self, db, now):
        previous = db.execute("SELECT value FROM service_metadata WHERE name='clock_high_water'").fetchone()
        if previous and now < int(previous[0]): raise RequestRejected(503,'service_unavailable')
        db.execute("INSERT OR REPLACE INTO service_metadata VALUES('clock_high_water',?)",(str(now),))

    def consume(self, call, now):
        def claim(db):
            self._clock(db,now)
            db.execute('DELETE FROM request_nonces WHERE expires_at < ?',(now,))
            if db.execute('SELECT 1 FROM request_nonces WHERE caller=? AND nonce=?',(call.caller,call.nonce)).fetchone():
                raise RequestRejected(409,'replay_rejected')
            db.execute('INSERT INTO request_nonces VALUES(?,?,?)',(call.caller,call.nonce,call.timestamp+FRESHNESS_SECONDS+1))
        self.sql.transaction(claim)

    def acquire(self, now):
        def claim(db):
            self._clock(db,now)
            previous = db.execute('SELECT owner,expires_at,fence FROM issuance_lease WHERE singleton=1').fetchone()
            if previous[0] is not None and previous[1] > now: raise RequestRejected(409,'issuance_busy')
            lease = Lease(secrets.token_hex(32),previous[2]+1)
            db.execute('UPDATE issuance_lease SET owner=?,expires_at=?,fence=? WHERE singleton=1',
                (lease.owner,now+LEASE_SECONDS,lease.fence))
            return lease
        return self.sql.transaction(claim)

    def assert_owner(self, lease, now, db=None):
        def check(connection):
            self._clock(connection,now)
            row = connection.execute('SELECT owner,expires_at,fence FROM issuance_lease WHERE singleton=1').fetchone()
            if row[0] != lease.owner or row[2] != lease.fence or row[1] <= now:
                raise RequestRejected(409,'issuance_lease_lost')
        if db is not None: return check(db)
        return self.sql.transaction(check)

    def release(self, lease):
        self.sql.transaction(lambda db: db.execute('UPDATE issuance_lease SET owner=NULL,expires_at=0 WHERE singleton=1 AND owner=? AND fence=?',
            (lease.owner,lease.fence)))


class DurableIssuanceDatabase:
    def __init__(self, sql, journal, lease, clock, identity):
        self.connection, self.journal, self.lease, self.clock = sql,journal,lease,clock
        self.storage_identity = identity + ':licences'
        def initialize(db):
            db.execute('CREATE TABLE IF NOT EXISTS storage_metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS signing_keys(kid TEXT PRIMARY KEY,public_key BLOB NOT NULL,domain TEXT NOT NULL,created_at TEXT NOT NULL,status TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS website_activation_licences(activation_request_id TEXT PRIMARY KEY,application_id TEXT NOT NULL,installation_id TEXT NOT NULL,device_public_key_hash TEXT NOT NULL,licence_id TEXT UNIQUE NOT NULL,envelope_json TEXT NOT NULL,audit_event_id TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS website_account_entitlements(application_id TEXT PRIMARY KEY,entitlement_id TEXT UNIQUE NOT NULL,snapshot_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS audit_events(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,timestamp TEXT NOT NULL,event_type TEXT NOT NULL,operator_id TEXT NOT NULL,affected_ids TEXT NOT NULL,details TEXT NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL)')
            # This runtime cannot contain legacy imported-request licences. Keep the
            # existing conflict query compatible without importing the desktop DB.
            db.execute('CREATE TABLE IF NOT EXISTS licences(licence_id TEXT PRIMARY KEY,application_id TEXT NOT NULL,revoked_at TEXT,expires_at INTEGER NOT NULL)')
        self.run_transaction(initialize)

    def run_transaction(self, action):
        def checked(db):
            self.journal.assert_owner(self.lease,int(self.clock()),db)
            result = action(db)
            self.journal.assert_owner(self.lease,int(self.clock()),db)
            return result
        return self.connection.transaction(checked)
