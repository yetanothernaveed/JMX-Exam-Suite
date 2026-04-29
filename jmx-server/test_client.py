"""
Test client for the multi-threaded TCP server.
Spawns N concurrent clients, each sending a sequence of commands
(including the blocking SLOW command) to prove concurrency works.

Usage:
    python tcp_client_test.py
    python tcp_client_test.py --host 127.0.0.1 --port 9000 --clients 10
"""

import socket
import threading
import time
import argparse
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("TestClient")

ENCODING   = "utf-8"
LINE_END   = "\r\n"


def talk(host: str, port: int, client_num: int, results: dict) -> None:
    """One simulated client session."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=15) as s:
            f = s.makefile("rb")

            def read() -> str:
                return f.readline().decode(ENCODING).strip()

            def send(cmd: str) -> None:
                s.sendall((cmd + LINE_END).encode(ENCODING))

            greeting = read()
            log.info("Client %2d  ← %s", client_num, greeting)

            # Send a mix of commands, including the 3-second SLOW one
            # for cmd in ["PING", "TIME", "ECHO hello from client", "SLOW", "QUIT"]:
            #     send(cmd)
            #     log.info("Client %2d  → %s", client_num, cmd)
            #     resp = read()
            #     log.info("Client %2d  ← %s", client_num, resp)
            #     if cmd == "SLOW":
            #         # Expect a progress line, then the result
            #         result = read()
            #         log.info("Client %2d  ← %s", client_num, result)
            with open("A.java", "r", encoding="utf-8") as file:
                code = file.read()
                size = len(code)
            
            print("Code", code)

            send(f"SUBMIT A.java java _313 {size}")
            send(code)
            read()

        elapsed = time.perf_counter() - start
        results[client_num] = ("OK", round(elapsed, 2))
    except Exception as exc:
        results[client_num] = ("ERR", str(exc))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host",    default="127.0.0.1")
    p.add_argument("--port",    default=9000, type=int)
    p.add_argument("--clients", default=1,    type=int,
                   help="Number of concurrent test clients")
    args = p.parse_args()

    results: dict = {}
    threads = [
        threading.Thread(
            target=talk,
            args=(args.host, args.port, i + 1, results),
            name=f"client-{i+1}",
        )
        for i in range(args.clients)
    ]

    wall_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall_elapsed = time.perf_counter() - wall_start

    print("\n─── Results ───────────────────────────")
    for cid, (status, info) in sorted(results.items()):
        print(f"  Client {cid:2d}: {status}  ({info}s)")

    print(f"\n  Total wall time : {wall_elapsed:.2f}s")
    print(f"  Clients run     : {args.clients}")
    print(
        f"\n  If wall time ≈ 3s (not {args.clients}×3s), concurrency is working ✓"
    )


if __name__ == "__main__":
    main()