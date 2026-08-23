import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_db_dir() -> None:
    db_dir = os.path.dirname(os.path.abspath(settings.sqlite_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)


@contextmanager
def get_conn():
    ensure_db_dir()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fake_accounts (
                customer_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS face_embeddings (
                customer_id TEXT PRIMARY KEY,
                embedding_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES fake_accounts(customer_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS face_verification_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                customer_id TEXT,
                liveness_passed INTEGER NOT NULL,
                face_score REAL,
                auth_status TEXT NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        count = conn.execute("SELECT COUNT(*) AS c FROM fake_accounts").fetchone()["c"]
        if count == 0:
            seed_rows = [
                ("acc_00981234", "Test Customer 1"),
                ("acc_00981235", "Test Customer 2"),
                ("acc_00981236", "Test Customer 3"),
                ("acc_00981237", "Test Customer 4"),
                ("acc_00981238", "Test Customer 5"),
                ("acc_00981239", "Test Customer 6"),
            ]
            conn.executemany(
                "INSERT INTO fake_accounts(customer_id, display_name) VALUES(?, ?)",
                seed_rows,
            )


def get_fake_accounts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT customer_id, display_name FROM fake_accounts ORDER BY customer_id"
        ).fetchall()
    return [dict(r) for r in rows]


def get_fake_account(customer_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT customer_id, display_name FROM fake_accounts WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
    return dict(row) if row else None


def upsert_face_embedding(customer_id: str, embedding: list[float]) -> None:
    now = utc_now_iso()
    embedding_json = json.dumps(embedding)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO face_embeddings(customer_id, embedding_json, created_at, updated_at)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(customer_id)
            DO UPDATE SET embedding_json = excluded.embedding_json,
                          updated_at = excluded.updated_at
            """,
            (customer_id, embedding_json, now, now),
        )


def list_face_embeddings() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT customer_id, embedding_json FROM face_embeddings"
        ).fetchall()
    return [
        {"customer_id": r["customer_id"], "embedding": json.loads(r["embedding_json"])}
        for r in rows
    ]


def log_face_verification(
    session_id: str,
    customer_id: str | None,
    liveness_passed: bool,
    face_score: float | None,
    auth_status: str,
    reason: str | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO face_verification_logs(
                session_id,
                customer_id,
                liveness_passed,
                face_score,
                auth_status,
                reason,
                created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                customer_id,
                1 if liveness_passed else 0,
                face_score,
                auth_status,
                reason,
                utc_now_iso(),
            ),
        )
