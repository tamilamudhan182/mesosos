"""Mesh-SOS node: UDP discovery, TCP anti-entropy exchange, gateway upload, web UI.

Run:  python -m node.node --name alice --port 7001 --web 8001
"""
import argparse, json, os, socket, threading, time, urllib.request, sys
from .message import Message, Identity
from .store import Store
from .routing import Predictability, initial_copies, should_forward, RESCUE

DISC_BASE = 47000           # discovery ports DISC_BASE .. DISC_BASE+DISC_RANGE-1
DISC_RANGE = 10

def battery_level(manual=None):
    if manual is not None:
        return float(manual)
    try:
        import psutil
        b = psutil.sensors_battery()
        if b is not None:
            return float(b.percent)
    except Exception:
        pass
    # Termux: termux-battery-status
    try:
        import subprocess
        out = subprocess.run(["termux-battery-status"], capture_output=True, text=True, timeout=3).stdout
        return float(json.loads(out)["percentage"])
    except Exception:
        return 100.0

def internet_ok(url):
    try:
        urllib.request.urlopen(url.rstrip("/") + "/api/ping", timeout=2); return True
    except Exception:
        return False

def _send_json(sock, obj):
    sock.sendall((json.dumps(obj) + "\n").encode())

def _recv_json(f):
    line = f.readline()
    if not line:
        raise ConnectionError("closed")
    return json.loads(line)


class Node:
    def __init__(self, name, port, data_dir="data", disc_port=None, battery=None,
                 dashboard=None, gateway=False, encounter_interval=3, verbose=True):
        self.name, self.port = name, port
        self.disc_port = disc_port or (DISC_BASE + (port % DISC_RANGE))
        self.manual_battery = battery
        self.dashboard = dashboard
        self.force_gateway = gateway
        self.interval = encounter_interval
        self.verbose = verbose
        d = os.path.join(data_dir, name); os.makedirs(d, exist_ok=True)
        self.ident = Identity(os.path.join(d, "key.pem"))
        self.store = Store(os.path.join(d, "store.db"))
        self.pred = Predictability()
        self.peers = {}          # name -> {addr, port, last_seen, battery, gateway}
        self.blocked = set()     # simulate partition: peers we refuse to talk to
        self.stats = {"sent": 0, "recv": 0, "uploaded": 0, "encounters": 0, "rejected_sig": 0}
        self.running = False
        self.lock = threading.Lock()

    # ---------- helpers ----------
    def log(self, ev, detail=""):
        self.store.log(ev, detail)
        if self.verbose:
            print(f"[{self.name}] {ev} {detail}", flush=True)

    @property
    def battery(self): return battery_level(self.manual_battery)

    def is_gateway(self):
        return bool(self.dashboard) and (self.force_gateway or internet_ok(self.dashboard))

    def create(self, text, mtype="SOS", lat=None, lon=None, urgency=3, people=1):
        m = Message(origin=self.name, type=mtype, text=text, lat=lat, lon=lon,
                    urgency=int(urgency), people=int(people)).sign(self.ident)
        m.hops = [self.name]
        self.store.add(m, initial_copies(mtype, m.urgency, self.battery))
        self.log("created", f"{m.type} {m.id} '{text}'")
        return m

    def hello(self):
        return {"type": "hello", "node": self.name, "battery": self.battery,
                "gateway": self.is_gateway(), "pred": dict(self.pred.p),
                "summary": self.store.ids(), "acks": sorted(self.store.acked())}

    # ---------- discovery ----------
    def _disc_listen(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", self.disc_port)); s.settimeout(1)
        while self.running:
            try:
                data, addr = s.recvfrom(2048)
                a = json.loads(data)
                if a.get("node") == self.name or a.get("app") != "meshsos":
                    continue
                with self.lock:
                    new = a["node"] not in self.peers
                    self.peers[a["node"]] = {"addr": addr[0], "port": a["port"], "last_seen": time.time(),
                                             "battery": a.get("battery"), "gateway": a.get("gateway")}
                if new:
                    self.log("discovered", f"{a['node']} @ {addr[0]}:{a['port']}")
            except socket.timeout:
                continue
            except Exception:
                continue

    def _disc_announce(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while self.running:
            pkt = json.dumps({"app": "meshsos", "node": self.name, "port": self.port,
                              "battery": self.battery, "gateway": bool(self.dashboard)}).encode()
            for p in range(DISC_BASE, DISC_BASE + DISC_RANGE):
                for host in ("255.255.255.255", "127.0.0.1"):
                    try: s.sendto(pkt, (host, p))
                    except Exception: pass
            time.sleep(2)

    # ---------- exchange (anti-entropy with routing decision) ----------
    def _select_for(self, peer_hello):
        """Pick messages the peer lacks, SOS first, filtered by PriorityAware rule."""
        have = set(peer_hello["summary"]); peer_acks = set(peer_hello["acks"])
        out = []
        my_p = self.pred.to_rescue()
        peer_p = float(peer_hello["pred"].get(RESCUE, 0.0))
        if peer_hello.get("gateway"): peer_p = 1.0
        for m, copies, delivered in self.store.all():       # already ordered by priority
            if m.id in have or m.id in peer_acks or m.expired():
                continue
            if peer_hello["node"] in m.hops:
                continue
            if delivered and m.type != "ACK":
                continue
            ok, give, keep = should_forward(m.type, copies, my_p, peer_p, peer_hello["battery"],
                                            peer_hello.get("gateway"))
            if ok:
                out.append((m, give)); self.store.set_copies(m.id, keep)
        return out

    def _absorb(self, peer_hello, msgs):
        for mid in peer_hello["acks"]:
            if mid not in self.store.acked():
                self.store.mark_acked(mid); self.log("ack-learned", mid)
        for d in msgs:
            m = Message.from_dict(d["msg"])
            if not m.verify():
                self.stats["rejected_sig"] += 1; self.log("bad-signature", m.id); continue
            if self.store.has(m.id) or m.id in self.store.acked():
                continue
            m.hops = list(m.hops) + [self.name]
            self.store.add(m, d["copies"])
            self.stats["recv"] += 1
            self.log("received", f"{m.type} {m.id} from {peer_hello['node']} hops={len(m.hops)-1}")

    def encounter(self, peer_name):
        """Initiator side of one contact."""
        if peer_name in self.blocked: return
        p = self.peers[peer_name]
        try:
            with socket.create_connection((p["addr"], p["port"]), timeout=4) as s:
                f = s.makefile("r")
                _send_json(s, self.hello())
                ph = _recv_json(f)
                if ph.get("blocked"): return
                self._update_pred(ph)
                out = self._select_for(ph)
                _send_json(s, {"type": "msgs", "msgs": [{"msg": m.to_dict(), "copies": c} for m, c in out]})
                self.stats["sent"] += len(out)
                reply = _recv_json(f)
                self._absorb(ph, reply["msgs"])
                self.stats["encounters"] += 1
        except Exception as e:
            if self.verbose: print(f"[{self.name}] encounter {peer_name} failed: {e}", flush=True)

    def _serve(self):
        srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self.port)); srv.listen(16); srv.settimeout(1)
        while self.running:
            try:
                c, _ = srv.accept()
            except socket.timeout:
                continue
            threading.Thread(target=self._handle, args=(c,), daemon=True).start()

    def _handle(self, c):
        try:
            with c:
                c.settimeout(5); f = c.makefile("r")
                ih = _recv_json(f)
                if ih["node"] in self.blocked:
                    _send_json(c, {"blocked": True}); return
                _send_json(c, self.hello())
                incoming = _recv_json(f)
                self._update_pred(ih)
                out = self._select_for(ih)
                _send_json(c, {"type": "msgs", "msgs": [{"msg": m.to_dict(), "copies": k} for m, k in out]})
                self.stats["sent"] += len(out)
                self._absorb(ih, incoming["msgs"])
        except Exception as e:
            if self.verbose: print(f"[{self.name}] handle failed: {e}", flush=True)

    def _update_pred(self, ph):
        with self.lock:
            self.pred.encounter(ph["node"], ph.get("pred", {}), bool(ph.get("gateway")))

    # ---------- gateway ----------
    def upload(self):
        if not self.is_gateway(): return 0
        n = 0
        for m, _, delivered in self.store.all():
            if delivered or m.type == "ACK": continue
            try:
                req = urllib.request.Request(self.dashboard.rstrip("/") + "/api/sos",
                                             data=json.dumps({"msg": m.to_dict(), "gateway": self.name}).encode(),
                                             headers={"Content-Type": "application/json"})
                r = json.loads(urllib.request.urlopen(req, timeout=4).read())
                if r.get("ok"):
                    self.store.mark_acked(m.id); n += 1; self.stats["uploaded"] += 1
                    self.log("uploaded", f"{m.id} -> dashboard")
            except Exception as e:
                self.log("upload-failed", str(e)); break
        return n

    def _loop(self):
        last_age = time.time()
        while self.running:
            time.sleep(self.interval)
            now = time.time()
            self.pred.age((now - last_age) / 30.0); last_age = now
            with self.lock:
                live = [n for n, p in self.peers.items() if now - p["last_seen"] < 10]
            # deterministic initiator rule halves duplicate sessions
            for pn in live:
                if self.name < pn or self.peers[pn].get("gateway"):
                    self.encounter(pn)
            self.upload()
            self.store.purge()

    def start(self):
        self.running = True
        for t in (self._serve, self._disc_listen, self._disc_announce, self._loop):
            threading.Thread(target=t, daemon=True).start()
        self.log("started", f"tcp={self.port} disc={self.disc_port} gateway={bool(self.dashboard)}")
        return self

    def stop(self): self.running = False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mesh-SOS node")
    ap.add_argument("--name", required=True)
    ap.add_argument("--port", type=int, default=7001, help="TCP exchange port")
    ap.add_argument("--web", type=int, default=8001, help="local web UI port (0=off)")
    ap.add_argument("--battery", type=float, default=None, help="manual battery %% (default: auto)")
    ap.add_argument("--dashboard", default=None, help="rescue dashboard URL -> gateway when reachable")
    ap.add_argument("--gateway", action="store_true", help="force gateway mode")
    ap.add_argument("--data", default="data")
    ap.add_argument("--cli", action="store_true", help="interactive CLI")
    ap.add_argument("--block", default="", help="comma list of peers to ignore (simulate distance)")
    a = ap.parse_args(argv)
    n = Node(a.name, a.port, a.data, battery=a.battery, dashboard=a.dashboard, gateway=a.gateway)
    n.blocked |= {b for b in a.block.split(",") if b}
    n.start()
    if a.web:
        from .web import serve
        threading.Thread(target=serve, args=(n, a.web), daemon=True).start()
        print(f"[{a.name}] web UI: http://127.0.0.1:{a.web}", flush=True)
    if a.cli:
        from .cli import repl
        repl(n)
    else:
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            n.stop()

if __name__ == "__main__":
    main()
