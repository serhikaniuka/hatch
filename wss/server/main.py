import asyncio
import functools
import logging

import websockets

from .cache import CacheClient
from .config import config
from .db import get_connection, initialize_schema
from .handler import connection_handler
from .mgmt import serve_mgmt
from .ssl_context import build_server_ssl_context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def serve() -> None:
    conn = get_connection(config.db_path)
    initialize_schema(conn)
    db_lock = asyncio.Lock()
    cache = CacheClient(
        config.memcached_host,
        config.memcached_port,
        ttl=config.client_state_ttl,
        max_recent=config.recent_connections_max,
    )
    ssl_ctx = build_server_ssl_context()

    handler = functools.partial(
        connection_handler,
        conn=conn,
        db_lock=db_lock,
        cache=cache,
        config=config,
    )

    logger.info("Starting WSS server on wss://%s:%s", config.host, config.port)
    async with websockets.serve(handler, config.host, config.port, ssl=ssl_ctx):
        await asyncio.gather(
            asyncio.Future(),
            serve_mgmt(cache),
        )


if __name__ == "__main__":
    asyncio.run(serve())
