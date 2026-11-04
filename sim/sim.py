"""Discrete-time DTN simulator for Mesh-SOS.

World: 3 km x 3 km flooded area, N mobile nodes (phones), G static rescue
gateways (relief camps with internet). Mobility: random waypoint OR community
(nodes mostly move inside a home community, sometimes roam). Each contact has a
limited transfer budget per step (Bluetooth/Wi-Fi Direct time is short), each
node has a finite buffer and a finite battery. Messages are destined to ANY gateway.

Protocols: epidemic, spray_wait (binary, L=8), prophet, priority (PriorityAware-DTN).
"""
import math, random
import numpy as np
from node.routing import P_INIT, BETA, GAMMA, initial_copies

class Msg:
    __slots__ = ("id", "src", "sos", "urg", "t0")
    def __init__(s, i, src, sos, urg, t0): s.id, s.src, s.sos, s.urg, s.t0 = i, src, sos, urg, t0

def run(protocol="priority", n=100, mobility="community", seed=1, steps=1800, dt=10.0,
        area=3000.0, rng_m=60.0, gateways=4, buffer=40, per_contact=4, msg_rate=0.25,
        sos_frac=0.25, ttl=4 * 3600, tx_cost=0.05, idle_cost=0.0015):
    R = random.Random(seed); np.random.seed(seed)
    N = n + gateways
    pos = np.random.rand(N, 2) * area
    gw = np.zeros(N, bool); gw[n:] = True
    pos[n:] = [[area * .2, area * .2], [area * .8, area * .8], [area * .2, area * .8], [area * .8, area * .2]][:gateways]
    # community model: 6 communities
    homes = np.random.rand(6, 2) * area; comm = np.random.randint(0, 6, N)
    target = pos.copy(); speed = np.random.uniform(0.5, 1.5, N)   # walking / wading m/s
    pause = np.zeros(N)
    battery = np.random.uniform(10, 100, N); battery[n:] = 1e9
    alive = np.ones(N, bool)
    buf = [dict() for _ in range(N)]          # id -> copies
    msgs = {}; delivered = {}; tx = 0; mid = 0
    P = [dict() for _ in range(N)]            # prophet table: node -> P ; key -1 = gateway
    acked = [set() for _ in range(N)]
    L_SW = 8

    def new_target(i):
        if mobility == "community" and R.random() < 0.8:
            return np.clip(homes[comm[i]] + np.random.randn(2) * 250, 0, area)
        return np.random.rand(2) * area

    def make_room(i, incoming_prio):
        b = buf[i]
        if len(b) < buffer: return True
        if protocol == "priority":   # drop lowest priority, oldest
            v = min(b, key=lambda k: (msgs[k].sos * 10 + msgs[k].urg, -(msgs[k].t0)))
            if msgs[v].sos * 10 + msgs[v].urg > incoming_prio: return False
        else:                        # FIFO drop oldest
            v = min(b, key=lambda k: msgs[k].t0)
        del b[v]; return True

    def pg(i): return 1.0 if gw[i] else P[i].get(-1, 0.0)

    for step in range(steps):
        t = step * dt
        # ---- mobility ----
        mob = ~gw & alive
        d = target - pos; dist = np.linalg.norm(d, axis=1)
        arrived = (dist < speed * dt) & mob
        for i in np.where(arrived)[0]:
            pause[i] -= dt
            if pause[i] <= 0: target[i] = new_target(i); pause[i] = R.uniform(0, 300)
        mv = mob & ~arrived
        pos[mv] += d[mv] / np.maximum(dist[mv], 1e-9)[:, None] * (speed[mv] * dt)[:, None]
        # ---- energy (idle scanning) ----
        battery[:n] -= idle_cost * dt
        alive = battery > 0
        # ---- generate messages ----
        for _ in range(np.random.poisson(msg_rate)):
            src = R.randrange(n)
            if not alive[src]: continue
            sos = R.random() < sos_frac
            m = Msg(mid, src, sos, R.randint(3, 5) if sos else R.randint(1, 2), t); msgs[mid] = m
            if protocol == "spray_wait": c = L_SW
            elif protocol == "priority": c = initial_copies("SOS" if sos else "INFO", m.urg, battery[src])
            else: c = 1
            if make_room(src, sos * 10 + m.urg): buf[src][mid] = c
            mid += 1
        # ---- expire / purge ----
        if step % 30 == 0:
            for i in range(N):
                for k in [k for k in buf[i] if t - msgs[k].t0 > ttl or k in delivered and protocol == "priority" and k in acked[i]]:
                    del buf[i][k]
            if protocol in ("prophet", "priority"):
                for i in range(n):
                    for k in P[i]: P[i][k] *= GAMMA ** 3
        # ---- contacts ----
        idx = np.where(alive)[0]; pp = pos[idx]
        dd = ((pp[:, None, :] - pp[None, :, :]) ** 2).sum(-1)
        ii, jj = np.where(np.triu(dd < rng_m ** 2, 1))
        order = list(zip(idx[ii], idx[jj])); R.shuffle(order)
        for a, b in order:
            if gw[a] and gw[b]: continue
            # prophet update
            if protocol in ("prophet", "priority"):
                for x, y in ((a, b), (b, a)):
                    if gw[x]: continue
                    o = P[x].get(y, 0); P[x][y] = o + (1 - o) * P_INIT
                    if gw[y]:
                        o = P[x].get(-1, 0); P[x][-1] = o + (1 - o) * P_INIT
                    else:
                        o = P[x].get(-1, 0); P[x][-1] = max(o, o + (1 - o) * P[x][y] * P[y].get(-1, 0) * BETA)
            if protocol == "priority":   # ack exchange (cheap, in summary vector)
                if gw[a] or gw[b]:
                    s = set(delivered)
                    for x in (a, b):
                        if not gw[x]: acked[x] |= {k for k in buf[x] if k in s}
                u = acked[a] | acked[b]; acked[a] = acked[b] = u
                for x in (a, b):
                    for k in [k for k in buf[x] if k in u]: del buf[x][k]
            for s_, r_ in ((a, b), (b, a)):
                if gw[s_]: continue
                budget = per_contact
                cand = [k for k in buf[s_] if k not in buf[r_] and k not in delivered or (gw[r_] and k not in delivered)]
                if protocol == "priority":
                    cand.sort(key=lambda k: -(msgs[k].sos * 10 + msgs[k].urg))
                else:
                    R.shuffle(cand)
                for k in cand:
                    if budget <= 0 or battery[s_] <= 0: break
                    if k in buf[r_]: continue
                    m = msgs[k]; c = buf[s_][k]
                    if gw[r_]:
                        delivered[k] = t - m.t0; del buf[s_][k]
                        tx += 1; budget -= 1; battery[s_] -= tx_cost; continue
                    give = None
                    if protocol == "epidemic": give, keep = 1, 1
                    elif protocol == "spray_wait":
                        if c > 1: give = c // 2; keep = c - give
                    elif protocol == "prophet":
                        if pg(r_) > pg(s_): give, keep = 1, 1
                    else:
                        from node.routing import should_forward
                        ok, g, kp = should_forward("SOS" if m.sos else "INFO", c, pg(s_), pg(r_), battery[r_], False)
                        if ok: give, keep = g, kp
                    if give is None or not make_room(r_, m.sos * 10 + m.urg): continue
                    buf[r_][k] = give; tx += 1; budget -= 1; battery[s_] -= tx_cost
                    if keep <= 0: del buf[s_][k]
                    else: buf[s_][k] = keep
    # ---- metrics (only messages old enough to have had a chance: created in first 75%) ----
    cut = steps * dt * 0.75
    eval_ids = [k for k, m in msgs.items() if m.t0 <= cut]
    def ratio(f):
        ids = [k for k in eval_ids if f(msgs[k])]
        return (sum(k in delivered for k in ids) / len(ids)) if ids else float("nan")
    lat = [delivered[k] for k in eval_ids if k in delivered]
    sos_lat = [delivered[k] for k in eval_ids if k in delivered and msgs[k].sos]
    return dict(protocol=protocol, n=n, mobility=mobility, seed=seed,
                delivery=ratio(lambda m: True), delivery_sos=ratio(lambda m: m.sos),
                delivery_info=ratio(lambda m: not m.sos),
                latency_min=(np.mean(lat) / 60 if lat else float("nan")),
                sos_latency_min=(np.mean(sos_lat) / 60 if sos_lat else float("nan")),
                overhead=tx / max(1, len(delivered)),
                energy_used=float(np.sum(np.clip(np.random.RandomState(seed).uniform(10, 100, n + gateways)[:n], 0, None)
                                         - np.clip(battery[:n], 0, None))) / n,
                dead_nodes=int(np.sum(battery[:n] <= 0)), messages=len(eval_ids))
