"""Build docs/report.docx from results/sim_summary.csv.  python docs/make_report.py"""
import csv, os
from docx import Document
from docx.shared import Inches
H = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = list(csv.DictReader(open(os.path.join(H, "results", "sim_summary.csv"))))
d = Document(); d.add_heading("Mesh-SOS: Priority-Aware Delay-Tolerant Disaster Mesh Network", 0)
def P(t): d.add_paragraph(t)
d.add_heading("Abstract", 1)
P("When cellular infrastructure fails during disasters, victims cannot request help. Mesh-SOS is a zero-cost, "
  "delay-tolerant (store-carry-forward) network built from ordinary laptops and Android phones. Nodes discover "
  "each other with UDP broadcast, exchange messages with a summary-vector anti-entropy protocol over TCP, store "
  "them persistently in SQLite, and upload them through any node that reaches the internet to a rescue dashboard. "
  "We propose PriorityAware-DTN, a routing scheme that orders by urgency, scales the copy budget by urgency and "
  "battery, weights copy splitting by PRoPHET delivery predictability, and purges delivered copies with ACKs. "
  "In simulation with 50–200 nodes it delivers 93–100% of SOS messages at 2–5x lower overhead than Epidemic "
  "flooding, at the cost of lower delivery of non-urgent messages.")
d.add_heading("1. Problem", 1)
P("In the December 2015 Chennai floods and Cyclone Michaung (December 2023) mobile towers lost power and backhaul; "
  "large areas had no voice or data for days while people were trapped on rooftops. Phones still had batteries and "
  "Wi-Fi radios, but no tool turned them into a rescue network that prioritises life-threatening requests and "
  "conserves battery.")
d.add_heading("2. Related work", 1)
for t in ["FireChat (Open Garden): Wi-Fi/Bluetooth mesh chat, used in 2014 Hong Kong protests; discontinued around 2018. General chat, no SOS priority.",
          "Bridgefy: Bluetooth mesh messenger; academic analyses (e.g. Albrecht et al., 2021) reported serious security flaws.",
          "Briar: secure peer-to-peer messenger over Bluetooth/Wi-Fi/Tor; strong security but designed for messaging between contacts, not urgency triage or rescue upload.",
          "Serval Project: mesh telephony for disaster relief; Wi-Fi ad-hoc often required rooted phones or extra hardware.",
          "Meshtastic / goTenna: long-range LoRa mesh; needs purchased radios.",
          "Classical DTN routing: Epidemic (Vahdat & Becker 2000), Spray-and-Wait (Spyropoulos et al. 2005), PRoPHET (Lindgren et al. 2003; RFC 6693)."]:
    d.add_paragraph(t, style="List Bullet")
d.add_heading("3. Novelty", 1)
for t in ["Routing that jointly uses urgency, battery level and delivery predictability (PriorityAware-DTN).",
          "Priority-based buffer management (drop lowest priority, not oldest) and per-contact priority ordering.",
          "End-to-end ACK propagation to purge copies and save battery.",
          "Signed messages end-to-end and a rescue-side triage dashboard (dedup, urgency ranking, map).",
          "Zero hardware cost: runs on Windows laptops and Android (Termux) with one hotspot as the shared medium."]:
    d.add_paragraph(t, style="List Bullet")
d.add_heading("4. System design", 1)
P("Node = discovery (UDP beacons every 2 s on ports 47000-47009), exchange server (TCP, JSON lines), SQLite store, "
  "routing module, gateway uploader, Flask UI. Dashboard = Flask + SQLite + Leaflet. Message = id, origin, type "
  "(SOS/INFO/ACK), urgency 1-5, people count, lat/lon, text, TTL, creation time, public key, Ed25519 signature, hop list (unsigned).")
d.add_heading("5. Protocol", 1)
for t in ["Encounter: initiator sends HELLO{ids, acks, battery, P-table, gateway flag}; responder replies HELLO; both send the messages the peer lacks, SOS first.",
          "Copy budget L = base(SOS 16, ACK 8, INFO 4) x (0.6+0.2*urgency) x (0.5 if battery<30%).",
          "Weighted spray: give w*L copies, w = P_peer/(P_peer+P_self) clipped to [0.2,0.8], reduced for low-battery peers.",
          "Battery gate: peers <15% accept only SOS, <5% accept nothing.",
          "Last copy: forwarded only to a peer with higher predictability; SOS keeps an insurance copy.",
          "Gateway uploads; the dashboard verifies the signature; acked IDs spread in HELLOs and delete copies."]:
    d.add_paragraph(t, style="List Number")
d.add_heading("6. Results", 1)
P("Simulator: 3 km x 3 km, 4 static gateways, 60 m radio range, 10 s step, 5 h, finite buffer (40 msgs), "
  "4 messages per contact per step, 25% of messages SOS, random battery 10-100%, 3 seeds, community and random-waypoint mobility.")
t = d.add_table(rows=1, cols=7); t.style = "Light Grid Accent 1"
for c, h in zip(t.rows[0].cells, ["Mobility", "Nodes", "Protocol", "SOS deliv.", "All deliv.", "SOS latency (min)", "Tx / delivered"]): c.text = h
for r in rows:
    c = t.add_row().cells
    vals = [r["mobility"], r["n"], r["protocol"], f'{float(r["delivery_sos"]):.2f}', f'{float(r["delivery"]):.2f}',
            f'{float(r["sos_latency_min"]):.1f}', f'{float(r["overhead"]):.1f}']
    for x, v in zip(c, vals): x.text = v
for f in ["comparison_community.png", "comparison_random_waypoint.png"]:
    p = os.path.join(H, "results", f)
    if os.path.exists(p): d.add_picture(p, width=Inches(6.3))
P("Interpretation (honest): PriorityAware-DTN wins clearly in sparse networks (50 nodes: SOS delivery 0.93-0.96 vs 0.70-0.87 for Epidemic) "
  "and always uses far fewer transmissions than Epidemic and PRoPHET. In dense networks (100-200 nodes) Epidemic and PRoPHET "
  "match or slightly beat it on SOS delivery and latency, but with 2-5x the transmissions and more battery. It deliberately sacrifices "
  "INFO messages (overall delivery 0.63-0.81). Spray-and-Wait has the lowest overhead but lower SOS delivery.")
P("Prototype test (one machine, 4 processes, line topology A-B-C-D): an SOS from A reached the dashboard through 3 hops in about 9 s; "
  "ACK returned to A; with the gateway switched off the SOS was stored on A, B and C and was delivered about 4 s after the gateway returned.")
d.add_heading("7. Limitations", 1)
for t in ["Simulation uses synthetic mobility and an energy proxy (fixed cost per transmission and per time unit), not real traces or measured power.",
          "The prototype uses a shared Wi-Fi hotspot as the link layer; true infrastructure-less Wi-Fi Direct/BLE needs a native Android app.",
          "No PKI: signatures prove integrity, not real-world identity; SOS spam from new keys is possible.",
          "Real multi-device field tests must be done by the team; numbers above are from simulation and localhost."]:
    d.add_paragraph(t, style="List Bullet")
d.add_heading("8. Conclusion and future work", 1)
P("Mesh-SOS shows that urgency- and battery-aware DTN routing can get SOS messages out of a disconnected disaster zone using only "
  "existing phones. Future work: native Android Wi-Fi Direct/BLE, LoRa relays, real mobility traces from campus tests, and rescue-agency key distribution.")
d.save(os.path.join(H, "docs", "report.docx")); print("wrote docs/report.docx")
