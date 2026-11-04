"""Per-node local web UI (open on the phone/laptop running the node)."""
from flask import Flask, request, jsonify, render_template_string
import logging

PAGE = """<!doctype html><html><head><meta name=viewport content="width=device-width,initial-scale=1">
<title>Mesh-SOS {{n.name}}</title><style>
body{font-family:sans-serif;max-width:760px;margin:auto;padding:10px;background:#111;color:#eee}
input,textarea,select,button{width:100%;padding:10px;margin:4px 0;font-size:16px;box-sizing:border-box}
button.sos{background:#d00;color:#fff;font-weight:bold;font-size:22px;border:0;border-radius:8px}
.m{border:1px solid #444;border-radius:6px;padding:6px;margin:4px 0}.SOS{border-color:#d33}
small{color:#aaa}</style></head><body>
<h2>Mesh-SOS node: {{n.name}}</h2>
<small>battery {{'%.0f'%n.battery}}% · peers {{peers|length}} · P(rescue) {{'%.2f'%n.pred.to_rescue()}} · gateway {{gw}}</small>
<form method=post action="/send">
<textarea name=text placeholder="What is your emergency?" required></textarea>
<input name=lat placeholder="latitude (e.g. 13.0827)"><input name=lon placeholder="longitude (e.g. 80.2707)">
<button type=button onclick="navigator.geolocation&&navigator.geolocation.getCurrentPosition(p=>{lat.value=p.coords.latitude;lon.value=p.coords.longitude})">Use my GPS</button>
<select name=urgency><option value=5>5 - life threatening</option><option value=4>4 - injured</option>
<option value=3 selected>3 - trapped/need rescue</option><option value=2>2 - need supplies</option><option value=1>1 - info</option></select>
<input name=people type=number value=1 min=1>
<select name=type><option>SOS</option><option>INFO</option></select>
<button class=sos>SEND</button></form>
<h3>Peers</h3>{% for k,v in peers.items() %}<div>{{k}} @ {{v.addr}}:{{v.port}} bat {{v.battery}}</div>{% endfor %}
<h3>Messages</h3>{% for m,c,d in msgs %}<div class="m {{m.type}}"><b>{{m.type}}</b> u{{m.urgency}} {{m.text}}<br>
<small>{{m.id}} from {{m.origin}} · path {{' → '.join(m.hops)}} · copies {{c}} · {{'DELIVERED ✔' if d else 'in transit'}}</small></div>{% endfor %}
<script>setInterval(()=>{const a=document.activeElement,t=document.querySelector("textarea");if((a&&a.matches("input,textarea,select"))||(t&&t.value.trim()))return;location.reload()},5000)</script></body></html>"""

def make_app(node):
    app = Flask(__name__)
    @app.get("/")
    def index():
        return render_template_string(PAGE, n=node, peers=dict(node.peers), msgs=node.store.all(),
                                      gw=bool(node.dashboard))
    @app.post("/send")
    def send():
        f = request.form
        fl = lambda k: float(f[k]) if f.get(k) else None
        node.create(f["text"], f.get("type", "SOS"), fl("lat"), fl("lon"), f.get("urgency", 3), f.get("people", 1))
        return '<meta http-equiv="refresh" content="0;url=/">'
    @app.post("/api/send")
    def api_send():
        j = request.get_json(force=True)
        m = node.create(j["text"], j.get("type", "SOS"), j.get("lat"), j.get("lon"), j.get("urgency", 3), j.get("people", 1))
        return jsonify(ok=True, id=m.id)
    @app.get("/api/state")
    def state():
        return jsonify(name=node.name, battery=node.battery, peers=node.peers, stats=node.stats,
                       p_rescue=node.pred.to_rescue(),
                       msgs=[dict(m.to_dict(), copies=c, delivered=d) for m, c, d in node.store.all()])
    @app.post("/api/block")
    def block():
        j = request.get_json(force=True)
        (node.blocked.add if j.get("block", True) else node.blocked.discard)(j["peer"])
        return jsonify(ok=True, blocked=sorted(node.blocked))
    return app

def serve(node, port):
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    make_app(node).run("0.0.0.0", port, threaded=True)
