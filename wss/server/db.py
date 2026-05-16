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
    # Migrate: add columns introduced after initial schema.
    # ALTER TABLE ADD COLUMN does not support UNIQUE — add the index separately.
    for stmt in [
        "ALTER TABLE clients ADD COLUMN client_num INTEGER",
        "ALTER TABLE clients ADD COLUMN hostname TEXT",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_num "
        "ON clients(client_num) WHERE client_num IS NOT NULL"
    )
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


def assign_client_num(conn: sqlite3.Connection, client_id: str) -> int:
    """Assign the next sequential number to a client if not already set."""
    row = conn.execute(
        "SELECT client_num FROM clients WHERE id = ?", (client_id,)
    ).fetchone()
    if row and row["client_num"] is not None:
        return row["client_num"]
    result = conn.execute(
        "SELECT COALESCE(MAX(client_num), 0) + 1 FROM clients"
    ).fetchone()
    next_num = result[0]
    conn.execute(
        "UPDATE clients SET client_num = ? WHERE id = ? AND client_num IS NULL",
        (next_num, client_id),
    )
    conn.commit()
    return next_num


def update_client_hostname(conn: sqlite3.Connection, client_id: str, hostname: str) -> None:
    conn.execute("UPDATE clients SET hostname = ? WHERE id = ?", (hostname, client_id))
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
