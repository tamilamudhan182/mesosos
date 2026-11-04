"""Tiny interactive CLI for a node."""
HELP = """commands:
  sos <text> [| lat,lon | urgency 1-5 | people]   e.g.  sos trapped on roof | 13.0827,80.2707 | 5 | 3
  info <text>          send non-urgent info
  list                 show stored messages
  peers                show discovered peers
  block <peer> / unblock <peer>   simulate a partition
  stats | quit"""

def repl(node):
    print(HELP)
    while True:
        try:
            line = input(f"{node.name}> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line: continue
        cmd, _, rest = line.partition(" ")
        if cmd == "sos" or cmd == "info":
            parts = [p.strip() for p in rest.split("|")]
            lat = lon = None; urg, ppl = 3, 1
            if len(parts) > 1 and "," in parts[1]:
                lat, lon = map(float, parts[1].split(","))
            if len(parts) > 2: urg = int(parts[2])
            if len(parts) > 3: ppl = int(parts[3])
            m = node.create(parts[0], "SOS" if cmd == "sos" else "INFO", lat, lon, urg, ppl)
            print("queued", m.id)
        elif cmd == "list":
            for m, c, d in node.store.all():
                print(f"{m.id} {m.type:4} u={m.urgency} copies={c:g} delivered={d} hops={'>'.join(m.hops)} :: {m.text}")
        elif cmd == "peers":
            for k, v in node.peers.items(): print(k, v)
        elif cmd == "block": node.blocked.add(rest); print("blocked", rest)
        elif cmd == "unblock": node.blocked.discard(rest); print("unblocked", rest)
        elif cmd == "stats": print(node.stats, "battery", node.battery, "P(rescue)=%.2f" % node.pred.to_rescue())
        elif cmd in ("quit", "exit"): break
        else: print(HELP)
    node.stop()
