import socket, threading, json, time, sys

TARGET_OFFSET = 20000
LOCAL_PORTS = (list(range(21110, 21116)) + list(range(22220, 22226))
               + list(range(26890, 26900)) + list(range(27890, 27900)))
OUT = sys.argv[1] if len(sys.argv) > 1 else "relay-capture.jsonl"

lock = threading.Lock()
f = open(OUT, "wb", buffering=0)

def log(port, direction, data):
    rec = {"t": time.time(), "port": port, "dir": direction, "n": len(data), "hex": data.hex()}
    with lock:
        f.write(json.dumps(rec).encode() + b"\n")

def connect_upstream(target_port, deadline=15.0):
    end = time.time() + deadline
    while time.time() < end:
        try:
            return socket.create_connection(("127.0.0.1", target_port), timeout=1)
        except OSError:
            time.sleep(0.05)
    return None

def pump(src, dst, port, direction):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            log(port, direction, data)
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try: dst.shutdown(socket.SHUT_WR)
        except OSError: pass

def handle(client, local_port):
    up = connect_upstream(local_port - TARGET_OFFSET)
    if up is None:
        log(local_port, "upstream-failed", b"")
        client.close()
        return
    t1 = threading.Thread(target=pump, args=(client, up, local_port, "c2s"), daemon=True)
    t2 = threading.Thread(target=pump, args=(up, client, local_port, "s2c"), daemon=True)
    t1.start(); t2.start()
    t1.join(); t2.join()
    client.close(); up.close()

for p in LOCAL_PORTS:
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", p))
    s.listen(8)
    threading.Thread(target=lambda s=s, p=p: [handle(c, p) for c in iter(s.accept, None)][0] if False else None, daemon=True).start()
    def serve(s=s, p=p):
        while True:
            c, _ = s.accept()
            threading.Thread(target=handle, args=(c, p), daemon=True).start()
    threading.Thread(target=serve, daemon=True).start()

print("relay listening on:", len(LOCAL_PORTS), "ports", flush=True)
time.sleep(float(sys.argv[2]) if len(sys.argv) > 2 else 120)
print("relay done", flush=True)
