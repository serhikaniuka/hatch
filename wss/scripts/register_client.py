#!/usr/bin/env python3
"""
Register a new client in the WSS server database.

Usage:
    python register_client.py [--db <path>] [--days <N>]

Prints only the UUID to stdout so it can be captured:
    CLIENT_UUID=$(python register_client.py --days 1)
"""
import argparse
import datetime
import sqlite3
import sys
import uuid
from pathlib import Path

DEFAULT_DB = str(Path(__file__).parent.parent / "server" / "wss.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a WSS client.")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    parser.add_argument("--days", type=int, default=1,
                        help="Enrollment window in days (default: 1)")
    args = parser.parse_args()

    if args.days < 1:
        print("Error: --days must be >= 1", file=sys.stderr)
        sys.exit(1)

    client_id = str(uuid.uuid4())
    allow_to = datetime.datetime.utcnow() + datetime.timedelta(days=args.days)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id         TEXT PRIMARY KEY,
                allow_to   TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO clients (id, allow_to) VALUES (?, ?)",
            (client_id, allow_to.strftime("%Y-%m-%dT%H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()

    print(client_id)


if __name__ == "__main__":
    main()
