"""Quick test: connect to SP plugin on port 7002 and send a simple command."""
import socket

HOST = "localhost"
PORT = 7002
TIMEOUT = 10

code = 'print("hello from test")\x00'

print(f"Connecting to {HOST}:{PORT}...")
try:
    with socket.create_connection((HOST, PORT), timeout=TIMEOUT) as s:
        print("Connected!")
        s.sendall(code.encode("utf-8"))
        print("Data sent. Waiting for response...")
        chunks = []
        while True:
            chunk = s.recv(4096)
            if not chunk:
                print("Connection closed by remote (no data).")
                break
            chunks.append(chunk)
            if b"\x00" in chunk:
                break
        response = b"".join(chunks).decode("utf-8", errors="replace").rstrip("\x00").strip()
        print(f"Response: {repr(response)}")
except ConnectionRefusedError:
    print("ERROR: Connection refused — plugin not running on port 7002.")
except TimeoutError:
    print("ERROR: Timed out — plugin accepted connection but never responded.")
except ConnectionResetError as e:
    print(f"ERROR: Connection reset — {e}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
