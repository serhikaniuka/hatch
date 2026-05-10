#!/usr/bin/env python3
import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from .config import config
from .enrollment import run_enrollment
from .persistent import run_persistent


async def main() -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)

    if config.is_enrolled():
        client_id = config.client_id_file.read_text().strip()
        print(f"[persistent] Connecting as client {client_id}")
        await run_persistent(client_id)
    else:
        client_id = os.environ.get("WSS_CLIENT_ID", "").strip()
        if not client_id:
            print(
                "Error: not enrolled. Set WSS_CLIENT_ID=<uuid> and re-run to enroll.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"[enrollment] Enrolling client {client_id}")
        await run_enrollment(client_id)
        print("Enrollment complete. Re-run (without WSS_CLIENT_ID) to start persistent connection.")


if __name__ == "__main__":
    asyncio.run(main())
