import json, sys, struct

recs = [json.loads(l) for l in open('relay-capture.jsonl')]
streams = {}
for r in recs:
    if r['n'] == 0:
        continue
    key = (r['port'], r['dir'])
    streams.setdefault(key, b'')
    streams[key] += bytes.fromhex(r['hex'])

GREET = bytes.fromhex('ff0000000000000001' '7f')

def parse_segment(seg):
    """Parse one ZMTP connection segment (starts with greeting). Returns (commands, messages)."""
    if not seg.startswith(GREET):
        return None
    i = 64  # greeting + NULL handshake padding
    commands, messages = [], []
    frames = []
    while i < len(seg):
        flags = seg[i]
        if flags & 0x02:
            if i + 9 > len(seg):
                break
            ln = struct.unpack('>Q', seg[i+1:i+9])[0]
            i += 9
        else:
            if i + 2 > len(seg):
                break
            ln = seg[i+1]
            i += 2
        body = seg[i:i+ln]
        i += ln
        if flags & 0x04:  # command
            commands.append(body)
        else:
            frames.append((flags, body))
            if not flags & 0x01:  # last frame of a message
                messages.append([b for _, b in frames])
                frames = []
    return commands, messages

def split_segments(buf):
    segs, starts = [], []
    i = 0
    while True:
        j = buf.find(GREET, i)
        if j < 0:
            break
        starts.append(j)
        i = j + 1
    for k, s in enumerate(starts):
        e = starts[k+1] if k + 1 < len(starts) else len(buf)
        segs.append(buf[s:e])
    return segs

def dump_label(msg):
    parts = []
    for b in msg:
        printable = all(32 <= c < 127 for c in b) if b else False
        parts.append(b.decode() if printable else b.hex())
    return ' | '.join(parts)

target = sys.argv[1] if len(sys.argv) > 1 else None
for key in sorted(streams):
    port, d = key
    if target and str(port) != target:
        continue
    buf = streams[key]
    segs = split_segments(buf)
    print(f'==== {key}: {len(buf)}B, {len(segs)} connection segments ====')
    total_msg = 0
    for si, seg in enumerate(segs):
        parsed = parse_segment(seg)
        if parsed is None:
            print(f'  seg{si}: not a greeting segment ({len(seg)}B) {seg[:32].hex()}')
            continue
        commands, messages = parsed
        cmds = [dump_label([c]) for c in commands]
        print(f'  seg{si}: {len(seg)}B, commands={cmds[:3]}{"..." if len(cmds)>3 else ""}, messages={len(messages)}')
        for msg in messages:
            total_msg += 1
            print(f'    MSG[{total_msg}] {dump_label(msg)[:220]}')
    print()
