"""Process entry point: boots the world, starts the listener and game tick.

C equivalent: src/main.c (``main()``, ``xmain()``, ``main_loop()``). This
replaces the C ``select()``-based event loop + SIGALRM tick with
``asyncio.start_server()`` and a plain asyncio task that sleeps 2 seconds
between ticks (pydirt/tick.py). The whole program is still single-threaded
and single-process, exactly like the C original - asyncio just cooperatively
interleaves client I/O and the tick within one thread instead of using
signals + select().
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
from pathlib import Path

import pydirt.commands  # noqa: F401  (import registers every @verb handler)
from pydirt import emotes, persistence, verbs
from pydirt.bootstrap import load_world
from pydirt.connection import handle_client
from pydirt.tick import tick_loop

logger = logging.getLogger("pydirt.server")

DEFAULT_PORT = 4000


async def run(data_dir: Path, port: int) -> None:
    world = load_world(data_dir)
    verbs.load_verb_table(data_dir / "verbs.src")
    emotes.load_emotes(data_dir / "actions")
    players_dir = data_dir / "players"

    async def on_client(reader, writer):
        await handle_client(reader, writer, world, players_dir)

    server = await asyncio.start_server(on_client, host="0.0.0.0", port=port)
    addrs = ", ".join(str(sock.getsockname()) for sock in server.sockets or [])
    logger.info("listening on %s", addrs)

    tick_task = asyncio.create_task(tick_loop(world))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows' event loop doesn't support add_signal_handler; Ctrl+C raises KeyboardInterrupt instead

    try:
        async with server:
            server_task = asyncio.create_task(server.serve_forever())
            await stop_event.wait()
            server_task.cancel()
    finally:
        logger.info("shutting down, saving connected players")
        world.running = False
        tick_task.cancel()
        for player in list(world.players.values()):
            persistence.save_player(players_dir, player)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="pydirt - a Python/asyncio port of DIRT 3.1")
    parser.add_argument("--data-dir", type=Path, default=Path("data"), help="path to the data/ directory")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port to listen on")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.data_dir, args.port))
    except KeyboardInterrupt:
        logger.info("interrupted, exiting")


if __name__ == "__main__":
    main()
