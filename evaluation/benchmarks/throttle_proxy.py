"""A TCP relay that imitates a constrained or stalling link, for browser playback tests.

Sits between the browser and the server. Bytes travelling *to the browser* are limited to
``--down-kbps`` and are held back completely for ``--stall-ms`` every ``--stall-every``
seconds; a fixed ``--delay-ms`` is added in each direction. Like a real connection, the
relay buffers whatever the sender writes, so an over-fast sender builds delay, not loss.

    python -m evaluation.benchmarks.throttle_proxy --listen 8766 --target 8765 \
        --down-kbps 1500 --delay-ms 150 --stall-every 6 --stall-ms 700
"""
from __future__ import annotations

import argparse
import asyncio
import time


async def pipe(reader, writer, kbps: float, delay_ms: float, stall_every: float, stall_ms: float):
    queue: asyncio.Queue = asyncio.Queue()
    start = time.perf_counter()

    async def pump():
        budget_at = time.perf_counter()        # time at which the link is free again
        while True:
            item = await queue.get()
            if item is None:
                break
            due, data = item
            now = time.perf_counter()
            wait = max(due, budget_at) - now
            if stall_every and stall_ms:
                phase = (max(now, now + wait) - start) % stall_every
                if phase < stall_ms / 1000:
                    wait = max(wait, 0) + (stall_ms / 1000 - phase)
            if wait > 0:
                await asyncio.sleep(wait)
            writer.write(data)
            await writer.drain()
            if kbps:
                budget_at = max(budget_at, time.perf_counter()) + len(data) * 8 / (kbps * 1000)
        writer.close()

    task = asyncio.create_task(pump())
    try:
        while True:
            data = await reader.read(2048)
            if not data:
                break
            await queue.put((time.perf_counter() + delay_ms / 1000, data))
    except (ConnectionError, asyncio.CancelledError):
        pass
    await queue.put(None)
    await task


async def main_async(a):
    async def handle(creader, cwriter):
        try:
            sreader, swriter = await asyncio.open_connection("127.0.0.1", a.target)
        except OSError:
            cwriter.close()
            return
        await asyncio.gather(
            pipe(creader, swriter, 0, a.delay_ms, 0, 0),                                   # browser -> server
            pipe(sreader, cwriter, a.down_kbps, a.delay_ms, a.stall_every, a.stall_ms),    # server -> browser
            return_exceptions=True)

    server = await asyncio.start_server(handle, "127.0.0.1", a.listen)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=8766)
    ap.add_argument("--target", type=int, default=8765)
    ap.add_argument("--down-kbps", type=float, default=0, help="0 = unlimited")
    ap.add_argument("--delay-ms", type=float, default=0)
    ap.add_argument("--stall-every", type=float, default=0, help="seconds between stalls")
    ap.add_argument("--stall-ms", type=float, default=0)
    asyncio.run(main_async(ap.parse_args()))
