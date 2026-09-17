"""
Local SQLite store for the kiosk agent.

Deliberately NOT a business database. It holds only what one kiosk needs:

    kiosk_config  identity snapshot confirmed by the Core API, small settings
    sessions      the current customer session (receipt number, timestamps)
    captures      photos taken but not yet sent (id, file name, times)
    outbox        one row per return submission (idempotency key, status)

No names, emails, payment details, prices or receipt contents are stored.
Nothing here can approve or refund anything: the outbox only records what
was sent and what the Core API answered.

Outbox status:  sending -> accepted | rejected | unconfirmed
                unconfirmed -> accepted | not_received   (after reconciliation)
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS kiosk_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    receipt_number TEXT,
    transaction_id TEXT,
    started_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL,
    ended_at TEXT
);
CREATE TABLE IF NOT EXISTS captures (
    capture_id TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    used_at TEXT
);
CREATE TABLE IF NOT EXISTS outbox (
    idempotency_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    session_id TEXT,
    transaction_id TEXT,
    item_id TEXT,
    quantity TEXT,
    response_code TEXT,
    refund_id TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

UNCONFIRMED = "unconfirmed"


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat()


class AgentStore:
    def __init__(self, path):
        self.path = str(path)
        self._lock = threading.Lock()
        if self.path != ":memory:":
            import os
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _exec(self, sql, params=()):
        with self._lock, self._connect() as conn:
            return conn.execute(sql, params).fetchall()

    # --- kiosk configuration ----------------------------------------------------
    def set_config(self, key, value):
        self._exec("INSERT INTO kiosk_config(key, value, updated_at) VALUES (?, ?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                   (key, json.dumps(value), iso(now())))

    def get_config(self, key):
        rows = self._exec("SELECT value, updated_at FROM kiosk_config WHERE key=?", (key,))
        if not rows:
            return None, None
        return json.loads(rows[0]["value"]), datetime.fromisoformat(rows[0]["updated_at"])

    # --- sessions ---------------------------------------------------------------------
    def current_session(self, timeout_seconds):
        rows = self._exec("SELECT * FROM sessions WHERE ended_at IS NULL "
                          "ORDER BY last_activity_at DESC LIMIT 1")
        if not rows:
            return None
        row = dict(rows[0])
        if datetime.fromisoformat(row["last_activity_at"]) < now() - timedelta(seconds=timeout_seconds):
            self.end_sessions()
            return None
        return row

    def touch_session(self, timeout_seconds, receipt_number=None, transaction_id=None):
        session = self.current_session(timeout_seconds)
        stamp = iso(now())
        if session is None or (receipt_number and session["receipt_number"] not in (None, receipt_number)):
            self.end_sessions()
            session_id = uuid.uuid4().hex
            self._exec("INSERT INTO sessions(session_id, receipt_number, transaction_id, started_at, "
                       "last_activity_at) VALUES (?, ?, ?, ?, ?)",
                       (session_id, receipt_number, transaction_id, stamp, stamp))
            return session_id
        self._exec("UPDATE sessions SET last_activity_at=?, receipt_number=COALESCE(?, receipt_number), "
                   "transaction_id=COALESCE(?, transaction_id) WHERE session_id=?",
                   (stamp, receipt_number, transaction_id, session["session_id"]))
        return session["session_id"]

    def end_sessions(self):
        self._exec("UPDATE sessions SET ended_at=? WHERE ended_at IS NULL", (iso(now()),))

    # --- captures -------------------------------------------------------------------
    def add_capture(self, capture_id, file_name):
        self._exec("INSERT INTO captures(capture_id, file_name, created_at) VALUES (?, ?, ?)",
                   (capture_id, file_name, iso(now())))

    def get_capture(self, capture_id):
        rows = self._exec("SELECT * FROM captures WHERE capture_id=?", (capture_id,))
        return dict(rows[0]) if rows else None

    def mark_capture_used(self, capture_id):
        self._exec("UPDATE captures SET used_at=? WHERE capture_id=?", (iso(now()), capture_id))

    def set_capture_created(self, capture_id, created_at):
        """Test helper: pretend a capture is older."""
        self._exec("UPDATE captures SET created_at=? WHERE capture_id=?", (iso(created_at), capture_id))

    # --- outbox ---------------------------------------------------------------------
    def outbox_start(self, key, kind, session_id, transaction_id, item_id, quantity):
        stamp = iso(now())
        self._exec(
            "INSERT INTO outbox(idempotency_key, kind, status, attempts, session_id, transaction_id, "
            "item_id, quantity, created_at, updated_at) VALUES (?, ?, 'sending', 1, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(idempotency_key) DO UPDATE SET status='sending', attempts=attempts+1, "
            "updated_at=excluded.updated_at",
            (key, kind, session_id, transaction_id, item_id, None if quantity is None else str(quantity),
             stamp, stamp))

    def outbox_finish(self, key, status, response_code=None, refund_id=None, error=None):
        self._exec("UPDATE outbox SET status=?, response_code=?, refund_id=COALESCE(?, refund_id), "
                   "last_error=?, updated_at=? WHERE idempotency_key=?",
                   (status, response_code, refund_id, error, iso(now()), key))

    def outbox_get(self, key):
        rows = self._exec("SELECT * FROM outbox WHERE idempotency_key=?", (key,))
        return dict(rows[0]) if rows else None

    def outbox_by_status(self, status):
        return [dict(r) for r in self._exec("SELECT * FROM outbox WHERE status=? ORDER BY created_at",
                                            (status,))]

    def outbox_counts(self):
        return {r["status"]: r["n"] for r in
                self._exec("SELECT status, count(*) AS n FROM outbox GROUP BY status")}
