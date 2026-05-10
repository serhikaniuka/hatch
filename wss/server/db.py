import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


def get_connection(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            id         TEXT PRIMARY KEY,
            allow_to   TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS client_certificates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id   TEXT NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            fingerprint TEXT NOT NULL UNIQUE,
            certificate TEXT NOT NULL,
            approved_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_certs_client
            ON client_certificates(client_id);
    """)
    conn.commit()


def get_client(conn: sqlite3.Connection, client_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, allow_to, created_at FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    return dict(row) if row else None


def create_client(conn: sqlite3.Connection, client_id: str, allow_to: datetime) -> None:
    conn.execute(
        "INSERT INTO clients (id, allow_to) VALUES (?, ?)",
        (client_id, allow_to.strftime("%Y-%m-%dT%H:%M:%S")),
    )
    conn.commit()


def get_cert_by_fingerprint(conn: sqlite3.Connection, fingerprint: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM client_certificates WHERE fingerprint = ?", (fingerprint,)
    ).fetchone()
    return dict(row) if row else None


def get_cert_by_client_id(conn: sqlite3.Connection, client_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM client_certificates WHERE client_id = ? ORDER BY approved_at DESC LIMIT 1",
        (client_id,),
    ).fetchone()
    return dict(row) if row else None


def store_certificate(
    conn: sqlite3.Connection, client_id: str, fingerprint: str, cert_pem: str
) -> None:
    conn.execute(
        "INSERT INTO client_certificates (client_id, fingerprint, certificate) VALUES (?, ?, ?)",
        (client_id, fingerprint, cert_pem),
    )
    conn.commit()
