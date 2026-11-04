# Mesh-SOS — a priority-aware disaster mesh network that needs no internet

When cell towers fail (Chennai floods 2015, Cyclone Michaung 2023) phones still have Wi-Fi radios.
Mesh-SOS turns laptops/phones into a **delay-tolerant network (DTN)**: every node *stores* messages,
*carries* them as people move, and *forwards* them when it meets another node. As soon as any node
reaches the internet it becomes a **gateway** and uploads SOS messages to a **rescue dashboard**.

Novel part: **PriorityAware-DTN routing** — SOS first, copy budget scaled by urgency and battery,
next hop weighted by PRoPHET-style "how likely is this peer to reach a rescue gateway", low-battery
phones refuse non-SOS load, and delivery ACKs flow back to purge copies. Every message is
**Ed25519-signed** so fake SOS / tampering is rejected.

Cost: ₹0 (your laptop + friends' phones + one phone hotspot with mobile data OFF).

## Folder map
| Path | What |
|---|---|
| `node/` | the real node: `message.py` (format+signatures), `store.py` (SQLite), `routing.py` (PriorityAware-DTN), `node.py` (UDP discovery, TCP anti-entropy, gateway), `web.py` (phone-friendly UI), `cli.py` |
| `dashboard/app.py` | rescue dashboard (Leaflet map, dedup, urgency ranking, live feed) |
| `sim/` | discrete-event simulator, 50–200 nodes, 4 protocols |
| `results/` | CSV + figures produced by the simulator |
| `demo.py` | one-machine demo: 4 nodes + dashboard, multi-hop + partition test |
| `tests/` | pytest |
| `docs/report.docx`, `docs/viva_qa.md` | report and viva prep |

## Step-by-step on Windows
1. Install **Python 3.10+** from python.org — tick **"Add python.exe to PATH"**.
2. Unzip `meshsos.zip`, open the `meshsos` folder.
3. Double-click **`setup.bat`** (needs internet once, ~2 min).
4. Double-click **`run_local_demo.bat`**. If Windows Firewall asks, click **Allow** (private networks).
   It starts dashboard (http://127.0.0.1:5000) and nodes A,B,C,D (UIs on ports 8001–8004) in a forced
   line A–B–C–D, sends test SOS from A, and prints:
   `PHASE 1 OK: SOS from A reached dashboard ... via path A -> B -> C -> D`, ACK back at A,
   then PHASE 2: gateway D is switched off, a new SOS is stored by A/B/C, D comes back and it is delivered.
   Leave it running and open the URLs to click around. Ctrl+C to stop.
5. **`run_sim.bat`** — runs the simulator (~1–2 min), writes `results/*.png` and `results/*.csv`.
   (`run_sim.bat --quick` for a 5-second version.)
6. **`run_tests.bat`** — 10 automated tests.
7. **`run_dashboard.bat`** / **`run_node.bat`** — for the real multi-device test below.

Manual commands (any OS): `python demo.py`, `python -m sim.run`, `python dashboard/app.py`,
`python -m node.node --name alice --port 7001 --web 8001 --cli`.

## Android (Termux, free on F-Droid)
```
pkg update && pkg install python python-cryptography git
pip install flask
# copy the meshsos folder to the phone (e.g. termux-setup-storage, then cp from ~/storage/downloads)
cd meshsos && bash run_termux.sh phone1
```
Open `http://127.0.0.1:8001` in the phone browser → big red SEND button, "Use my GPS" button.
(psutil is optional; install `pkg install termux-api` + the Termux:API app to read real battery, else
pass `--battery 60` manually. The simulator/report need numpy/matplotlib — run those on the laptop.)

## Real multi-device test (the part that gives you REAL data)
Setup: one phone makes a **hotspot with mobile data OFF** (no internet = disaster). 3–5 laptops/phones join it.
1. On the "rescue" laptop: `run_dashboard.bat`. Note its IP (`ipconfig`, e.g. 192.168.43.20).
2. On each device: `run_node.bat` (or `run_termux.sh`). Give a unique name. On ONE device that will be the
   gateway, enter dashboard URL `http://192.168.43.20:5000`.
3. Check each node's UI shows the others under **Peers** (UDP broadcast discovery on ports 47000–47009).
4. **Direct test:** send SOS from a phone → appears on the dashboard map within seconds.
5. **Walk-away partition test:** take the gateway device out of hotspot range (or type `block <peer>` in the CLI).
   Send SOS from another phone — check `list`: it is *stored*. Walk a carrier phone to the gateway (or join
   the gateway to a second hotspot with that carrier) → message delivered; ACK returns and copies are purged.
6. **Battery test:** start one node with `--battery 10`; send INFO and SOS — it should carry SOS only.
7. What to log for your report (all in `data/<node>/store.db`, table `log`, and the dashboard API
   `http://IP:5000/api/sos`): creation time, delivery time (latency), hop path, number of copies
   (`stats` command), failed encounters, battery % before/after, distance walked. Do ≥10 SOS per scenario.
   Take screenshots/video of the map.

Troubleshooting: no peers → allow Python in Windows Firewall (Private), make sure all devices are on the
same hotspot, some hotspots block client-to-client traffic ("AP isolation") — try another phone.

## Honest limitations
- Simulation results are synthetic (mobility models, not real traces). See report.
- Discovery/exchange uses one shared Wi-Fi hotspot; real phone-to-phone Wi-Fi Direct/Bluetooth without any
  hotspot would need an Android app (future work).
- Keys are per-node; there is no PKI, so signatures prove integrity/consistency of the sender, not real identity.
