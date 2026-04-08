"""
Substance Painter MCP Socket Plugin

Runs inside SP, opens a TCP socket on localhost:7002.
Code execution uses a main-thread polling queue (QTimer on main thread
checks a queue every 50ms) so SP API is always called on the main thread.

Installation:
    Copy to both SP plugin locations and reload plugins in SP.
"""

import io
import json
import queue
import socket
import sys
import threading
import traceback

import substance_painter.logging as sp_logging

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HOST = "localhost"
PORT = 7002
BUFFER_SIZE = 65536
MAX_CODE_SIZE = 4 * 1024 * 1024
EXEC_TIMEOUT = 120
POLL_INTERVAL_MS = 50   # how often main thread checks the work queue

# ---------------------------------------------------------------------------
# Work queue: socket threads post jobs here; main thread processes them
# ---------------------------------------------------------------------------
_work_queue = queue.Queue()


def _get_qtimer():
    try:
        from PySide6.QtCore import QTimer
        return QTimer
    except ImportError:
        pass
    try:
        from PySide2.QtCore import QTimer
        return QTimer
    except ImportError:
        pass
    return None


def _run_code(code: str) -> str:
    """Execute code string, capture stdout, return result. Runs on main thread."""
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        import importlib
        exec_globals = {
            "__builtins__": __builtins__,
            "json": json,
            "traceback": traceback,
        }
        for attr, mod_name in [
            ("sp_project",  "substance_painter.project"),
            ("sp_ts",       "substance_painter.textureset"),
            ("sp_ls",       "substance_painter.layerstack"),
            ("sp_export",   "substance_painter.export"),
            ("sp_baking",   "substance_painter.baking"),
            ("sp_resource", "substance_painter.resource"),
            ("sp_logging",  "substance_painter.logging"),
        ]:
            try:
                exec_globals[attr] = importlib.import_module(mod_name)
            except Exception:
                pass
        exec(code, exec_globals)
        output = buf.getvalue()
        return output.strip() if output.strip() else "OK"
    except Exception:
        return "ERROR: " + traceback.format_exc()
    finally:
        sys.stdout = old_stdout


def _poll_work_queue():
    """Called by QTimer on the main thread every POLL_INTERVAL_MS ms."""
    try:
        while True:
            code, result_holder, done_event = _work_queue.get_nowait()
            try:
                result_holder["result"] = _run_code(code)
            except Exception:
                result_holder["result"] = "ERROR: " + traceback.format_exc()
            finally:
                done_event.set()
    except queue.Empty:
        pass


# ---------------------------------------------------------------------------
# Socket server
# ---------------------------------------------------------------------------
class SPSocketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._server_socket = None
        self._thread = None
        self._running = False
        self._poll_timer = None

    def start(self):
        if self._running:
            return
        self._running = True

        # Start the main-thread polling timer
        QTimer = _get_qtimer()
        if QTimer is not None:
            self._poll_timer = QTimer()
            self._poll_timer.timeout.connect(_poll_work_queue)
            self._poll_timer.start(POLL_INTERVAL_MS)
            sp_logging.log(sp_logging.INFO, "SP MCP Plugin",
                           "Main-thread poll timer started (QTimer).")
        else:
            sp_logging.log(sp_logging.WARNING, "SP MCP Plugin",
                           "No QTimer available — will execute code directly on socket thread.")

        # Start background socket server thread
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        sp_logging.log(sp_logging.INFO, "SP MCP Plugin",
                       f"Socket server started on {self.host}:{self.port}")

    def stop(self):
        self._running = False
        if self._poll_timer is not None:
            try:
                self._poll_timer.stop()
            except Exception:
                pass
            self._poll_timer = None
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        sp_logging.log(sp_logging.INFO, "SP MCP Plugin", "Socket server stopped.")

    def _serve(self):
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(5)
            self._server_socket.settimeout(1.0)
            while self._running:
                try:
                    conn, addr = self._server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
                t.start()
        except Exception:
            sp_logging.log(sp_logging.ERROR, "SP MCP Plugin",
                           "Socket server error:\n" + traceback.format_exc())

    def _handle(self, conn):
        try:
            chunks = []
            total = 0
            while True:
                chunk = conn.recv(BUFFER_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_CODE_SIZE:
                    conn.sendall(b"ERROR: Request too large\x00")
                    return
                chunks.append(chunk)
                if b"\x00" in chunk:
                    break

            raw = b"".join(chunks)
            code = raw.rstrip(b"\x00").decode("utf-8", errors="replace").strip()

            if not code:
                conn.sendall(b"OK\x00")
                return

            # If QTimer is available, dispatch via work queue (main thread)
            if self._poll_timer is not None:
                result_holder = {}
                done_event = threading.Event()
                _work_queue.put((code, result_holder, done_event))
                done_event.wait(timeout=EXEC_TIMEOUT)
                if not done_event.is_set():
                    result = f"ERROR: Execution timed out after {EXEC_TIMEOUT}s"
                else:
                    result = result_holder.get("result", "OK")
            else:
                # No QTimer — run directly on socket thread (fallback)
                result = _run_code(code)

            conn.sendall((result + "\x00").encode("utf-8"))
        except Exception:
            try:
                conn.sendall(("ERROR: " + traceback.format_exc() + "\x00").encode("utf-8"))
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------------------
_server = SPSocketServer(HOST, PORT)


def start_plugin():
    _server.start()
    sp_logging.log(sp_logging.INFO, "SP MCP Plugin",
                   f"MCP socket plugin loaded. Listening on {HOST}:{PORT}.")


def close_plugin():
    _server.stop()
    sp_logging.log(sp_logging.INFO, "SP MCP Plugin", "MCP socket plugin unloaded.")


if __name__ == "__main__":
    import time
    print(f"SP MCP Plugin: starting on {HOST}:{PORT} (test mode)")
    _server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _server.stop()
