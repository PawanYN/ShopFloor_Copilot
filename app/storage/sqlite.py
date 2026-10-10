import hashlib
import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The audit tables are append-only: feedback and approvals arrive as new event rows,
# and the triggers reject any edit or delete. Each row also carries a fingerprint that
# covers the row before it, so a change made around the triggers is still detected.
SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    inputs TEXT NOT NULL,
    defect_category TEXT,
    ocr_text TEXT,
    config TEXT NOT NULL,
    trace TEXT NOT NULL,
    answer TEXT NOT NULL,
    result TEXT NOT NULL,
    latency_seconds REAL NOT NULL,
    previous_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id TEXT NOT NULL REFERENCES transactions(id),
    created_at TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);

-- The score sheet changes with every feedback; its full history is kept in learning_updates.
CREATE TABLE IF NOT EXISTS learning_values (
    state TEXT NOT NULL,
    action INTEGER NOT NULL,
    value REAL NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (state, action)
);

CREATE TABLE IF NOT EXISTS learning_updates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    transaction_id TEXT,
    state TEXT NOT NULL,
    action INTEGER NOT NULL,
    reward REAL NOT NULL,
    value_after REAL NOT NULL
);

CREATE TRIGGER IF NOT EXISTS learning_updates_no_update BEFORE UPDATE ON learning_updates
BEGIN SELECT RAISE(ABORT, 'learning_updates is append-only'); END;

CREATE TRIGGER IF NOT EXISTS learning_updates_no_delete BEFORE DELETE ON learning_updates
BEGIN SELECT RAISE(ABORT, 'learning_updates is append-only'); END;

CREATE TRIGGER IF NOT EXISTS transactions_no_update BEFORE UPDATE ON transactions
BEGIN SELECT RAISE(ABORT, 'transactions is append-only'); END;

CREATE TRIGGER IF NOT EXISTS transactions_no_delete BEFORE DELETE ON transactions
BEGIN SELECT RAISE(ABORT, 'transactions is append-only'); END;

CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events is append-only'); END;
"""

JSON_COLUMNS = ("inputs", "config", "trace", "payload", "result")
CHAINED = {
    "transactions": ("id", "created_at", "inputs", "defect_category", "ocr_text", "config", "trace", "answer", "result", "latency_seconds"),
    "events": ("transaction_id", "created_at", "type", "payload"),
}
FIRST_HASH = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    record = {key: row[key] for key in row.keys() if key not in ("previous_hash", "hash")}
    for column in JSON_COLUMNS:
        if column in record:
            record[column] = json.loads(record[column])
    return record


def _fingerprint(previous_hash: str, values: list[Any]) -> str:
    return hashlib.sha256((previous_hash + json.dumps(values)).encode()).hexdigest()


class SqliteStore:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _writing(self):
        """One writer at a time, so two rows can never claim the same previous fingerprint."""
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")

    def _append(self, conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
        last = conn.execute(f"SELECT hash FROM {table} ORDER BY rowid DESC LIMIT 1").fetchone()
        previous_hash = last["hash"] if last else FIRST_HASH
        columns = CHAINED[table]
        row = [values[column] for column in columns]
        marks = ", ".join("?" for _ in range(len(columns) + 2))
        conn.execute(
            f"INSERT INTO {table} ({', '.join(columns)}, previous_hash, hash) VALUES ({marks})",
            (*row, previous_hash, _fingerprint(previous_hash, row)),
        )

    def verify_chain(self) -> dict[str, Any]:
        """Recompute every fingerprint. A changed or removed row breaks the chain from that point on."""
        report = {}
        with closing(self._connect()) as conn:
            for table, columns in CHAINED.items():
                previous_hash, count, broken_at = FIRST_HASH, 0, None
                for row in conn.execute(f"SELECT rowid AS position, * FROM {table} ORDER BY rowid"):
                    expected = _fingerprint(previous_hash, [row[column] for column in columns])
                    if row["previous_hash"] != previous_hash or row["hash"] != expected:
                        broken_at = row["position"]
                        break
                    previous_hash, count = row["hash"], count + 1
                report[table] = {"intact": broken_at is None, "rows_checked": count, "broken_at_row": broken_at}
        return report

    def add_transaction(self, record: dict[str, Any]) -> None:
        with self._writing() as conn:
            self._append(
                conn,
                "transactions",
                {
                    "id": record["id"],
                    "created_at": _now(),
                    "inputs": json.dumps(record["inputs"]),
                    "defect_category": record.get("defect_category"),
                    "ocr_text": record.get("ocr_text"),
                    "config": json.dumps(record["config"]),
                    "trace": json.dumps(record["trace"]),
                    "answer": record["answer"],
                    "result": json.dumps(record["result"]),
                    "latency_seconds": record["latency_seconds"],
                },
            )

    def get_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
        return _decode(row) if row else None

    def add_event(self, transaction_id: str, event_type: str, payload: dict[str, Any]) -> None:
        with self._writing() as conn:
            self._append(
                conn,
                "events",
                {"transaction_id": transaction_id, "created_at": _now(), "type": event_type, "payload": json.dumps(payload)},
            )

    def list_events(self, transaction_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, created_at, type, payload FROM events WHERE transaction_id = ? ORDER BY id",
                (transaction_id,),
            ).fetchall()
        return [_decode(row) for row in rows]

    def learning_values(self, state: str) -> dict[int, dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT action, value, count FROM learning_values WHERE state = ?", (state,)).fetchall()
        return {row["action"]: {"value": row["value"], "count": row["count"]} for row in rows}

    def save_learning_update(
        self, state: str, action: int, reward: float, value: float, count: int, transaction_id: str | None
    ) -> None:
        with self._writing() as conn:
            conn.execute(
                "INSERT INTO learning_values (state, action, value, count) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (state, action) DO UPDATE SET value = excluded.value, count = excluded.count",
                (state, action, value, count),
            )
            conn.execute(
                "INSERT INTO learning_updates (created_at, transaction_id, state, action, reward, value_after)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (_now(), transaction_id, state, action, reward, value),
            )

    def learning_history(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM learning_updates ORDER BY id").fetchall()
        return [dict(row) for row in rows]
