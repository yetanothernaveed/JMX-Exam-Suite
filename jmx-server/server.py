"""
Multi-threaded TCP/IP Socket Server
====================================
Handles multiple client connections concurrently using a thread pool.
Each client connection gets its own dedicated thread, allowing blocking
operations within handlers without affecting other clients.

Usage:
    python tcp_server.py                        # Start with defaults (host=0.0.0.0, port=9000)
    python tcp_server.py --host 127.0.0.1 --port 8080 --workers 20
"""

import socket
import threading
import logging
import argparse
import time
import signal
import sys
import subprocess
import tempfile
import os
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from execute import execute_from_disk

# ─────────────────────────────────────────────
#  Logging setup
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("TCPServer")


# ─────────────────────────────────────────────
#  Protocol helpers  (CRLF-delimited messages)
# ─────────────────────────────────────────────
BUFFER_SIZE   = 4096
LINE_ENDING = b"\r\n"
ENCODING      = "utf-8"
MAX_FILE_SIZE = 5 * 1024 * 1024


def recv_to_file(conn: socket.socket, target_path: Path, n: int) -> bool:
    """
    Streams exactly n bytes from the socket directly to a file.
    Returns true if successful, False if the connection closed early
    """
    bytes_remaining = n
    try:
        with open(target_path, "wb") as f:
            while bytes_remaining > 0:
                chunk_size = min(bytes_remaining, BUFFER_SIZE)
                chunk = conn.recv(chunk_size)

                print("Received this code chunk")
                print(chunk)

                if not chunk:
                    return False
                
                f.write(chunk)
                bytes_remaining -= chunk
        return True
    except OSError:
        return False
    
def recv_line(conn: socket.socket, timeout: float = 30.0) -> str | None:
    """
    Read one newline-terminated line from *conn*.
 
    Blocks until a complete line arrives, the connection closes, or *timeout*
    seconds elapse (simulating a realistic blocking I/O scenario).
 
    Returns the decoded line (stripped) or None on disconnect / timeout.
    """
    conn.settimeout(timeout)
    buf = b""
    try:
        while True:
            chunk = conn.recv(BUFFER_SIZE)
            if not chunk:           # peer closed connection
                return None
            buf += chunk
            if LINE_ENDING in buf:
                line, _ = buf.split(LINE_ENDING, 1)
                return line.decode(ENCODING).strip()
    except (socket.timeout, ConnectionResetError, BrokenPipeError):
        return None



def send_line(conn: socket.socket, message: str) -> bool:
    """Send *message* followed by CRLF. Returns False on send failure."""
    try:
        conn.sendall((message + "\r\n").encode(ENCODING))
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


# ─────────────────────────────────────────────
#  Request handler  (runs in its own thread)
# ─────────────────────────────────────────────

COMMANDS = {
    "PING":  "PONG",
    "TIME":  None,          # dynamic — filled at runtime
    "ECHO":  None,          # echoes the argument
    "SLOW":  None,          # simulates a blocking operation (sleep 3 s)
    "QUIT":  None,
    "HELP":  None,
}

def handle_client(conn: socket.socket, addr: tuple, client_id: int) -> None:
    
    peer = f"{addr[0]}:{addr[1]}"
    log.info("Client #%d connected  (%s)", client_id, peer)

    with conn:
        # ── Greeting ──────────────────────────────────
        if not send_line(conn, f"220 Welcome! You are client #{client_id}. Type HELP for commands."):
            return

        while True:
            # ── Blocking read — only THIS thread waits ─
            raw = recv_line(conn)

            if raw is None:
                log.info("Client #%d disconnected (%s)", client_id, peer)
                break

            if not raw:
                continue

            parts   = raw.split()        # split into command + optional arg
            cmd     = parts[0].upper()

            log.info("Client #%d ← %r", client_id, raw)

            # ── Command dispatch ───────────────────────
            if cmd == "SUBMIT":
                if len(parts) < 5:
                    send_line(conn, "400 Usage: SUBMIT <filename> <lang> <problem_id> <bytes>")
                    continue

                filename = parts[1] # example: Solution.java or A.py or Q1.cpp Anything
                lang = parts[2].lower() # example: java or python or cpp
                problem_id = parts[3].lower() # example: _323 
                
                try:
                    num_bytes = int(parts[4])
                except ValueError:
                    send_line(conn, "400 Invalid byte count")
                    continue
                
                if num_bytes > MAX_FILE_SIZE:
                    send_line(conn, f"413 File too large (Max {MAX_FILE_SIZE} bytes)")
                    continue

                with tempfile.TemporaryDirectory() as tmpdir:
                    work_dir = Path(tmpdir)

                    file_path = work_dir / filename

                    # send_line(conn, "100 Ready for payload")

                    # Stream directly to disk
                    if not recv_to_file(conn, file_path, num_bytes):
                        log.error("Streaming failed for client #%d", client_id)
                        return

                    output = execute_from_disk(lang, filename, work_dir, problem_id)
                    output_bytes = output.encode(ENCODING)
                    send_line(conn, f"LEN: {len(output_bytes)}")
                    conn.sendall(output_bytes) 
                

            elif cmd == "PING":
                send_line(conn, "PONG")

            elif cmd == "TIME":
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                send_line(conn, f"200 {now}")

            elif cmd == "ECHO":
                send_line(conn, f"200 echo worked")

            elif cmd == "SLOW":
                # ── Simulated blocking operation ───────
                # While this thread sleeps, ALL other client threads keep running.
                send_line(conn, "102 Processing… (sleeping 3 s to simulate blocking I/O)")
                time.sleep(3)                   # ← blocking — isolated to this thread
                send_line(conn, "200 Done with slow operation")

            elif cmd == "QUIT":
                send_line(conn, "221 Bye!")
                log.info("Client #%d quit gracefully (%s)", client_id, peer)
                break

            elif cmd == "HELP":
                help_text = (
                    "200 Commands: "
                    "PING | TIME | ECHO <text> | SLOW | QUIT | HELP"
                )
                send_line(conn, help_text)

            else:
                send_line(conn, f"500 Unknown command: {cmd!r}")


# ─────────────────────────────────────────────
#  Server
# ─────────────────────────────────────────────

class TCPServer:
    """
    Multi-threaded TCP server backed by a ThreadPoolExecutor.

    Each accepted connection is submitted as a task to the pool.
    The OS schedules threads so blocking in one handler never delays others.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9000,
        max_workers: int = 50,
        backlog: int = 10,
    ):
        self.host        = host
        self.port        = port
        self.max_workers = max_workers
        self.backlog     = backlog

        self._server_sock: socket.socket
        self._pool:        ThreadPoolExecutor
        self._shutdown     = threading.Event()
        self._client_count = 0
        self._lock         = threading.Lock()

    # ── Lifecycle ─────────────────────────────
    def start(self) -> None:
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(self.backlog)
        self._server_sock.settimeout(1.0)   # non-blocking accept loop

        self._pool = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="worker",
        )

        log.info(
            "Server listening on %s:%d  (max_workers=%d)",
            self.host, self.port, self.max_workers,
        )

        self._accept_loop()

    def stop(self) -> None:
        log.info("Shutdown requested …")
        self._shutdown.set()

    # ── Accept loop  (main thread) ────────────
    def _accept_loop(self) -> None:
        try:
            while not self._shutdown.is_set():
                try:
                    conn, addr = self._server_sock.accept()
                except socket.timeout:
                    continue            # check shutdown flag and retry

                with self._lock:
                    self._client_count += 1
                    cid = self._client_count

                # Submit to thread pool — non-blocking from main thread's POV
                self._pool.submit(handle_client, conn, addr, cid)

        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        log.info("Closing server socket …")
        if self._server_sock:
            self._server_sock.close()

        log.info("Waiting for active handlers to finish …")
        if self._pool:
            self._pool.shutdown(wait=True, cancel_futures=False)

        log.info("Server stopped. Total clients served: %d", self._client_count)


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-threaded TCP/IP socket server")
    p.add_argument("--host",    default="0.0.0.0",  help="Bind address (default: 0.0.0.0)")
    p.add_argument("--port",    default=9000, type=int, help="Bind port (default: 9000)")
    p.add_argument("--workers", default=50,   type=int, help="Max concurrent threads (default: 50)")
    p.add_argument("--backlog", default=10,   type=int, help="Socket listen backlog (default: 10)")
    return p.parse_args()


def main() -> None:
    args   = parse_args()
    server = TCPServer(
        host=args.host,
        port=args.port,
        max_workers=args.workers,
        backlog=args.backlog,
    )

    # Graceful shutdown on Ctrl-C / SIGTERM
    def _sig_handler(sig, _frame):
        server.stop()

    signal.signal(signal.SIGINT,  _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    server.start()


if __name__ == "__main__":
    main()