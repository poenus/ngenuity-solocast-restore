import sys, time, json, os
import zmq

out_path = sys.argv[1]
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 50.0

ctx = zmq.Context.instance()
socks = []
for port in (2220, 7890):
    s = ctx.socket(zmq.SUB)
    s.setsockopt(zmq.SUBSCRIBE, b"")
    s.setsockopt(zmq.LINGER, 0)
    s.connect(f"tcp://127.0.0.1:{port}")
    socks.append((port, s))

poller = zmq.Poller()
for _, s in socks:
    poller.register(s, zmq.POLLIN)

records = []
deadline = time.time() + duration
with open(out_path, "wb") as f:
    while time.time() < deadline:
        events = dict(poller.poll(200))
        for port, s in socks:
            if s in events:
                try:
                    while True:
                        frames = s.recv_multipart(zmq.NOBLOCK)
                        ts = time.time()
                        rec = {"t": ts, "port": port, "frames": [fr.hex() for fr in frames]}
                        f.write(json.dumps(rec).encode() + b"\n")
                        f.flush()
                except zmq.Again:
                    pass
print(f"captured {0} records", file=sys.stderr)
