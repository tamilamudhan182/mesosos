import time, json
from node.message import Message, Identity
from node.store import Store
from node.routing import Predictability, initial_copies, should_forward, RESCUE
from node.node import Node
from dashboard.app import create_app
from sim.sim import run

def test_sign_verify_and_tamper(tmp_path):
    ident = Identity(str(tmp_path / "k.pem"))
    m = Message(origin="a", text="help", urgency=5).sign(ident)
    assert m.verify()
    m2 = Message.from_dict(json.loads(json.dumps(m.to_dict()))); m2.hops.append("x")
    assert m2.verify(), "hop list is not signed (changes en route)"
    m2.text = "fake"; assert not m2.verify()

def test_identity_persistent(tmp_path):
    assert Identity(str(tmp_path / "k.pem")).pub == Identity(str(tmp_path / "k.pem")).pub

def test_store_dedup_ack_expiry(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    m = Message(origin="a", text="x")
    assert s.add(m, 4) and not s.add(m, 4)
    s.mark_acked(m.id); assert m.id in s.acked()
    old = Message(origin="a", text="old", ttl=1, created=time.time() - 10); s.add(old, 1)
    assert s.purge() == 1 and not s.has(old.id)

def test_priority_order(tmp_path):
    s = Store(str(tmp_path / "s.db"))
    s.add(Message(origin="a", type="INFO", text="i", urgency=1), 1)
    s.add(Message(origin="a", type="SOS", text="s", urgency=5), 1)
    assert s.all()[0][0].type == "SOS"

def test_copy_budget():
    assert initial_copies("SOS", 5, 90) > initial_copies("INFO", 1, 90)
    assert initial_copies("SOS", 5, 10) < initial_copies("SOS", 5, 90)

def test_forward_rules():
    assert should_forward("INFO", 1, 0.1, 0.9, 10, False)[0] is False      # low battery peer refuses INFO
    assert should_forward("SOS", 8, 0.1, 0.9, 10, False)[0] is True        # but accepts SOS
    ok, give, keep = should_forward("SOS", 8, 0.2, 0.8, 90, False); assert give + keep == 8 and give > keep
    assert should_forward("INFO", 3, 0, 0, 50, True) == (True, 3, 0)       # gateway gets all

def test_predictability():
    p = Predictability(); p.encounter("g", {}, True); a = p.to_rescue(); p.age(10)
    assert 0 < p.to_rescue() < a

def test_two_node_exchange(tmp_path):
    a = Node("a", 17101, str(tmp_path), battery=80, verbose=False)
    b = Node("b", 17102, str(tmp_path), battery=80, verbose=False)
    b.running = True
    import threading; threading.Thread(target=b._serve, daemon=True).start(); time.sleep(0.3)
    m = a.create("trapped", urgency=5)
    a.peers["b"] = {"addr": "127.0.0.1", "port": 17102, "last_seen": time.time(), "battery": 80, "gateway": False}
    a.encounter("b"); time.sleep(0.3)
    got, copies = b.store.get(m.id)
    assert got and got.hops == ["a", "b"] and copies >= 1
    b.running = False

def test_dashboard_dedup_and_sig(tmp_path):
    c = create_app(str(tmp_path / "d.db")).test_client()
    ident = Identity(str(tmp_path / "k.pem"))
    m = Message(origin="a", text="roof", urgency=5, lat=13.0, lon=80.2).sign(ident)
    for _ in range(3): assert c.post("/api/sos", json={"msg": m.to_dict(), "gateway": "g"}).json["ok"]
    low = Message(origin="b", text="food", urgency=2).sign(ident)
    c.post("/api/sos", json={"msg": low.to_dict(), "gateway": "g"})
    r = c.get("/api/sos").json
    assert len(r["cases"]) == 2 and r["reports"] == 4 and r["cases"][0]["text"] == "roof"
    bad = m.to_dict(); bad["text"] = "tampered"
    assert c.post("/api/sos", json={"msg": bad}).status_code == 400

def test_sim_runs_all_protocols():
    for p in ["epidemic", "spray_wait", "prophet", "priority"]:
        r = run(p, n=30, steps=200, seed=1)
        assert 0 <= r["delivery"] <= 1 and r["messages"] > 0
