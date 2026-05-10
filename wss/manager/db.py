import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def create_client(conn: sqlite3.Connection, days: int = 1) -> str:
    client_id = str(uuid.uuid4())
    allow_to = datetime.now(timezone.utc) + timedelta(days=days)
    conn.execute(
        "INSERT INTO clients (id, allow_to) VALUES (?, ?)",
        (client_id, allow_to.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    conn.commit()
    return client_id


def list_clients(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("""
        SELECT c.id, c.allow_to, c.created_at,
               cc.fingerprint, cc.approved_at
        FROM clients c
        LEFT JOIN client_certificates cc ON c.id = cc.client_id
        ORDER BY c.created_at DESC
    """).fetchall()
    return [dict(r) for r in rows]


def get_client(conn: sqlite3.Connection, client_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    return dict(row) if row else None


def get_cert(conn: sqlite3.Connection, client_id: str) -> Optional[dict]:
    row = conn.execute(
        """SELECT * FROM client_certificates
           WHERE client_id = ?
           ORDER BY approved_at DESC LIMIT 1""",
        (client_id,),
    ).fetchone()
    return dict(row) if row else None


def update_allow_to(conn: sqlite3.Connection, client_id: str, days: int = 1) -> bool:
    allow_to = datetime.now(timezone.utc) + timedelta(days=days)
    cur = conn.execute(
        "UPDATE clients SET allow_to = ? WHERE id = ?",
        (allow_to.strftime("%Y-%m-%dT%H:%M:%S"), client_id),
    )
    conn.commit()
    return cur.rowcount > 0


def revoke_cert(conn: sqlite3.Connection, client_id: str) -> bool:
    cur = conn.execute(
        "DELETE FROM client_certificates WHERE client_id = ?", (client_id,)
    )
    conn.commit()
    return cur.rowcount > 0
