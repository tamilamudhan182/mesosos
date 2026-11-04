"""Mesh-SOS local demo: 4 nodes + rescue dashboard on one machine.

Topology is forced to a LINE  A - B - C - D(gateway)  by making nodes ignore
non-neighbours, so an SOS from A must travel 3 hops to reach the dashboard.
Phase 2 shows store-carry-forward: gateway D is OFF while E's SOS spreads;
D comes back later and the stored copies are delivered.

  python demo.py            # run, verify, open browser
  python demo.py --no-browser --timeout 90
"""
import argparse, json, os, shutil, subprocess, sys, time, urllib.request, webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
DASH = "http://127.0.0.1:5000"
NODES = [  # name, tcp, web, battery, blocks, gateway
    ("A", 7001, 8001, 80, "C,D", False),
    ("B", 7002, 8002, 25, "D", False),
    ("C", 7003, 8003, 60, "A", False),
    ("D", 7004, 8004, 90, "A,B", True),
]

def get(url):
    return json.loads(urllib.request.urlopen(url, timeout=3).read())

def post(url, obj):
    r = urllib.request.Request(url, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=3).read())

def wait_up(url, t=30):
    end = time.time() + t
    while time.time() < end:
        try: get(url); return True
        except Exception: time.sleep(0.5)
    return False

def spawn(args, logname):
    os.makedirs(os.path.join(HERE, "data", "logs"), exist_ok=True)
    f = open(os.path.join(HERE, "data", "logs", logname), "w")
    return subprocess.Popen([PY] + args, cwd=HERE, stdout=f, stderr=subprocess.STDOUT)

def start_node(n, dd):
    name, tcp, web, bat, blk, gw = n
    a = ["-m", "node.node", "--name", name, "--port", str(tcp), "--web", str(web),
         "--battery", str(bat), "--block", blk, "--data", dd]
    if gw: a += ["--dashboard", DASH, "--gateway"]
    return spawn(a, f"node_{name}.log")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--timeout", type=int, default=90); ap.add_argument("--keep", action="store_true",
                    help="keep everything running after the check (Ctrl+C to stop)")
    a = ap.parse_args()
    dd = os.path.join(HERE, "data", "demo"); shutil.rmtree(dd, ignore_errors=True)
    procs = [spawn(["dashboard/app.py", "--db", os.path.join(dd, "dashboard.db")], "dashboard.log")]
    ok = True
    try:
        assert wait_up(DASH + "/api/ping"), "dashboard did not start"
        procs += [start_node(n, dd) for n in NODES]
        for n in NODES: assert wait_up(f"http://127.0.0.1:{n[2]}/api/state"), f"node {n[0]} did not start"
        print("Dashboard  :", DASH)
        for n in NODES: print(f"Node {n[0]} UI  : http://127.0.0.1:{n[2]}")
        if not a.no_browser: webbrowser.open(DASH)

        # Phase 1: multi-hop delivery
        sos = post("http://127.0.0.1:8001/api/send", {"text": "Family of 4 trapped on roof, water rising",
                   "lat": 13.0418, "lon": 80.2341, "urgency": 5, "people": 4})["id"]
        post("http://127.0.0.1:8001/api/send", {"text": "Road near Velachery bridge flooded", "type": "INFO",
             "lat": 12.9791, "lon": 80.2209, "urgency": 1})
        post("http://127.0.0.1:8002/api/send", {"text": "Elderly man needs insulin", "lat": 13.0604,
             "lon": 80.2496, "urgency": 4, "people": 1})
        t0 = time.time(); case = None
        while time.time() - t0 < a.timeout:
            cases = get(DASH + "/api/sos")["cases"]
            case = next((c for c in cases if c["id"] == sos), None)
            if case: break
            time.sleep(1)
        if case:
            print(f"PHASE 1 OK: SOS from A reached dashboard in {time.time()-t0:.1f}s via path {' -> '.join(case['hops'])}")
        else:
            print("PHASE 1 FAILED: SOS not delivered"); ok = False
        # wait for ack to travel back to A
        t1 = time.time(); acked = False
        while time.time() - t1 < 30:
            st = get("http://127.0.0.1:8001/api/state")
            if any(m["id"] == sos and m["delivered"] for m in st["msgs"]): acked = True; break
            time.sleep(1)
        print("ACK back at origin A:", "yes (copies purged)" if acked else "NO"); ok &= acked

        # Phase 2: store-carry-forward across a partition (gateway offline)
        procs[-1].terminate(); procs[-1].wait()
        print("PHASE 2: gateway D switched OFF (network partition)")
        sos2 = post("http://127.0.0.1:8003/api/send", {"text": "Pregnant woman needs hospital", "lat": 13.0012,
                    "lon": 80.2565, "urgency": 5, "people": 2})["id"]
        time.sleep(10)
        held = [n[0] for n in NODES[:3] if any(m["id"] == sos2 for m in get(f"http://127.0.0.1:{n[2]}/api/state")["msgs"])]
        print("  SOS held (stored) by nodes while no gateway:", held)
        procs[-1] = start_node(NODES[3], dd)
        print("  gateway D back ON")
        t2 = time.time(); d2 = False
        while time.time() - t2 < a.timeout:
            if any(c["id"] == sos2 for c in get(DASH + "/api/sos")["cases"]): d2 = True; break
            time.sleep(1)
        print(f"PHASE 2 {'OK' if d2 else 'FAILED'}: stored SOS delivered after reconnection"
              + (f" in {time.time()-t2:.1f}s" if d2 else "")); ok &= d2

        r = get(DASH + "/api/sos")
        print(f"Dashboard: {len(r['cases'])} unique cases, {r['reports']} reports")
        for i, c in enumerate(r["cases"], 1):
            print(f"  #{i} score={c['score']:.1f} u={c['urgency']} {c['text']}  path={'->'.join(c['hops'])}")
        print("RESULT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
        if a.keep:
            print("Running. Open the URLs above. Press Ctrl+C to stop.")
            while True: time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
