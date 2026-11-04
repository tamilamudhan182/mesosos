"""PriorityAware-DTN routing (shared by the real node and the simulator).

Decision inputs: message priority/urgency, own & peer battery, PRoPHET-style
delivery predictability toward the rescue gateway, and a per-message copy budget.
"""
P_INIT, BETA, GAMMA = 0.75, 0.25, 0.98
RESCUE = "RESCUE"

class Predictability:
    def __init__(self):
        self.p = {}        # dest -> P(me, dest)

    def age(self, k=1.0):
        for d in list(self.p):
            self.p[d] *= GAMMA ** k

    def encounter(self, peer, peer_table, peer_is_gateway=False):
        old = self.p.get(peer, 0.0)
        self.p[peer] = old + (1 - old) * P_INIT
        if peer_is_gateway:
            o = self.p.get(RESCUE, 0.0); self.p[RESCUE] = o + (1 - o) * P_INIT
        pab = self.p[peer]
        for d, pbc in peer_table.items():
            if d == "__self__":
                continue
            o = self.p.get(d, 0.0)
            self.p[d] = max(o, o + (1 - o) * pab * pbc * BETA)

    def to_rescue(self): return self.p.get(RESCUE, 0.0)


def initial_copies(mtype, urgency, battery):
    """Copy budget L: SOS gets more copies, urgency scales it, low battery shrinks it."""
    base = {"SOS": 16, "ACK": 8}.get(mtype, 4)
    u = 0.6 + 0.2 * max(1, min(5, urgency or 1))        # 0.8..1.6
    b = 0.5 if battery < 30 else 1.0
    return max(2, round(base * u * b))


def should_forward(mtype, copies, my_p, peer_p, peer_battery, peer_is_gateway):
    """Return (forward?, copies_to_give, copies_to_keep)."""
    if peer_is_gateway:
        return True, copies, 0
    if peer_battery < 15 and mtype != "SOS":
        return False, 0, copies          # don't burden nearly dead phones
    if peer_battery < 5:
        return False, 0, copies
    if copies > 1:
        # weighted spray: give more copies to the better carrier
        w = 0.5
        if peer_p + my_p > 0:
            w = min(0.8, max(0.2, peer_p / (peer_p + my_p)))
        if peer_battery < 30:
            w *= 0.6
        give = max(1, int(copies * w)) if copies >= 2 else 1
        give = min(give, int(copies) - 1) if copies >= 2 else 0
        if give >= 1:
            return True, give, copies - give
        return False, 0, copies
    # single copy left: hand over (forward, not replicate) only if peer is clearly better
    if peer_p > my_p + 0.05 and peer_battery >= 20:
        return True, 1, 0 if mtype != "SOS" else 1  # SOS: keep a copy as insurance
    return False, 0, copies
