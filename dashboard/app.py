"""Rescue dashboard: receives SOS from gateway nodes, dedups, ranks by urgency, Leaflet map."""
import json, os, sqlite3, sys, time, threading, logging
from flask import Flask, request, jsonify, render_template_string
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from node.message import Message

PAGE = """<!doctype html><html><head><title>Mesh-SOS Rescue Dashboard</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<link rel=stylesheet href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{margin:0;font-family:sans-serif;display:flex;height:100vh}#map{flex:2}#side{flex:1;overflow:auto;padding:8px;background:#fafafa}
.c{border-left:6px solid #999;padding:6px;margin:6px 0;background:#fff}.u5{border-color:#b00}.u4{border-color:#e50}.u3{border-color:#e90}
.u2{border-color:#cc0}.u1{border-color:#6a6}small{color:#666}</style></head><body>
<div id=map></div><div id=side><h2>Rescue queue</h2><div id=stats></div><div id=list></div></div>
<script>
let map=null,layer=null;
try{map=L.map('map').setView([13.0827,80.2707],12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OSM'}).addTo(map);
layer=L.layerGroup().addTo(map);}catch(e){document.getElementById('map').innerHTML='<p style=padding:20px>Map tiles need internet; list still works.</p>'}
async function load(){const r=await (await fetch('/api/sos')).json();
document.getElementById('stats').innerHTML=`<b>${r.cases.length}</b> unique cases · ${r.reports} reports received (${r.reports-r.cases.length} duplicates merged)`;
let h='';if(layer)layer.clearLayers();
r.cases.forEach((c,i)=>{h+=`<div class="c u${c.urgency}"><b>#${i+1} score ${c.score.toFixed(1)}</b> · urgency ${c.urgency} · ${c.people} people<br>${c.text}<br>
<small>${c.origin} · ${c.lat??'?'},${c.lon??'?'} · ${c.hops.join(' → ')} · via ${c.gateway} · waited ${Math.round(c.age/60)} min · ${c.reports} report(s)</small></div>`;
if(layer&&c.lat!=null)L.circleMarker([c.lat,c.lon],{radius:6+c.urgency*2,color:['','#6a6','#cc0','#e90','#e50','#b00'][c.urgency]}).bindPopup(`#${i+1} ${c.text}`).addTo(layer)});
document.getElementById('list').innerHTML=h}
load();setInterval(load,3000)</script></body></html>"""

def score(c, now):
    """Urgency ranking: urgency dominates, more people and longer wait raise priority."""
    return c["urgency"] * 10 + min(c["people"], 20) * 1.0 + min((now - c["created"]) / 600, 10)

def create_app(db_path="data/dashboard.db"):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    db = sqlite3.connect(db_path, check_same_thread=False); lock = threading.Lock()
    db.execute("CREATE TABLE IF NOT EXISTS sos(id TEXT PRIMARY KEY, body TEXT, gateway TEXT, t REAL, reports INT)")
    db.execute("CREATE TABLE IF NOT EXISTS stats(k TEXT PRIMARY KEY, v INT)"); db.commit()
    app = Flask(__name__)

    @app.get("/")
    def index(): return render_template_string(PAGE)

    @app.get("/api/ping")
    def ping(): return jsonify(ok=True)

    @app.post("/api/sos")
    def post():
        j = request.get_json(force=True); m = Message.from_dict(j["msg"])
        if not m.verify():
            return jsonify(ok=False, error="bad signature"), 400
        with lock:
            db.execute("INSERT INTO stats VALUES('reports',1) ON CONFLICT(k) DO UPDATE SET v=v+1")
            if db.execute("SELECT 1 FROM sos WHERE id=?", (m.id,)).fetchone():
                db.execute("UPDATE sos SET reports=reports+1 WHERE id=?", (m.id,))
            else:
                db.execute("INSERT INTO sos VALUES(?,?,?,?,1)", (m.id, json.dumps(m.to_dict()), j.get("gateway"), time.time()))
            db.commit()
        return jsonify(ok=True)

    @app.get("/api/sos")
    def get():
        now = time.time()
        with lock:
            rows = db.execute("SELECT body,gateway,t,reports FROM sos").fetchall()
            rep = (db.execute("SELECT v FROM stats WHERE k='reports'").fetchone() or [0])[0]
        cases = {}
        for b, gw, t, n in rows:
            d = json.loads(b)
            if d["type"] == "ACK": continue
            # semantic dedup: same origin re-sending the same text = one case
            key = (d["origin"], d["text"].strip().lower())
            c = cases.get(key)
            if c:
                c["reports"] += n; c["urgency"] = max(c["urgency"], d["urgency"]); continue
            d.update(gateway=gw, received=t, reports=n, age=now - d["created"],
                     delivery_latency=t - d["created"]); cases[key] = d
        out = sorted(cases.values(), key=lambda c: -score(c, now))
        for c in out: c["score"] = score(c, now)
        return jsonify(cases=out, reports=rep)
    return app

def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--db", default="data/dashboard.db"); a = ap.parse_args()
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    print(f"Rescue dashboard: http://127.0.0.1:{a.port}", flush=True)
    create_app(a.db).run("0.0.0.0", a.port, threaded=True)

if __name__ == "__main__":
    main()
