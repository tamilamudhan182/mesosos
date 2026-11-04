"""Run the protocol comparison and write results/*.csv + results/*.png.
   python -m sim.run            (full: 50/100/200 nodes x 2 mobility x 3 seeds)
   python -m sim.run --quick
"""
import argparse, csv, os, time
from collections import defaultdict
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from .sim import run

PROTOS = ["epidemic", "spray_wait", "prophet", "priority"]
LABEL = {"epidemic": "Epidemic", "spray_wait": "Spray&Wait", "prophet": "PRoPHET", "priority": "PriorityAware (ours)"}
METRICS = [("delivery_sos", "SOS delivery ratio"), ("delivery", "Overall delivery ratio"),
           ("sos_latency_min", "SOS latency (min)"), ("overhead", "Transmissions per delivered msg"),
           ("energy_used", "Battery used per node (%)"), ("delivery_info", "INFO delivery ratio")]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--quick", action="store_true"); ap.add_argument("--out", default="results")
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    sizes = [50, 100] if a.quick else [50, 100, 200]
    seeds = [1] if a.quick else [1, 2, 3]
    mobs = ["community"] if a.quick else ["community", "random_waypoint"]
    steps = 900 if a.quick else 1800
    rows = []
    for mob in mobs:
        for n in sizes:
            for s in seeds:
                for p in PROTOS:
                    t = time.time(); r = run(p, n=n, mobility=mob, seed=s, steps=steps); rows.append(r)
                    print(f"{mob:15} n={n:3} seed={s} {p:10} SOS={r['delivery_sos']:.3f} all={r['delivery']:.3f} "
                          f"lat={r['sos_latency_min']:.1f}m ovh={r['overhead']:.1f} energy={r['energy_used']:.1f} ({time.time()-t:.1f}s)", flush=True)
    with open(os.path.join(a.out, "sim_raw.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    agg = defaultdict(list)
    for r in rows: agg[(r["mobility"], r["n"], r["protocol"])].append(r)
    summary = []
    for (mob, n, p), rs in sorted(agg.items()):
        d = {"mobility": mob, "n": n, "protocol": p}
        for k, _ in METRICS + [("latency_min", ""), ("dead_nodes", "")]:
            v = np.array([x[k] for x in rs], float); d[k] = float(np.nanmean(v)); d[k + "_std"] = float(np.nanstd(v))
        summary.append(d)
    with open(os.path.join(a.out, "sim_summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
    for mob in mobs:
        fig, axs = plt.subplots(2, 3, figsize=(14, 8))
        for ax, (k, title) in zip(axs.flat, METRICS):
            x = np.arange(len(sizes)); wdt = 0.2
            for i, p in enumerate(PROTOS):
                vals = [next(s[k] for s in summary if s["mobility"] == mob and s["n"] == n and s["protocol"] == p) for n in sizes]
                err = [next(s[k + "_std"] for s in summary if s["mobility"] == mob and s["n"] == n and s["protocol"] == p) for n in sizes]
                ax.bar(x + (i - 1.5) * wdt, vals, wdt, yerr=err, label=LABEL[p], capsize=2)
            ax.set_xticks(x); ax.set_xticklabels([f"{n} nodes" for n in sizes]); ax.set_title(title); ax.grid(axis="y", alpha=.3)
        axs[0, 0].legend(fontsize=8); fig.suptitle(f"Mesh-SOS DTN routing comparison ({mob} mobility, mean ± std over {len(seeds)} seeds)")
        fig.tight_layout(); fig.savefig(os.path.join(a.out, f"comparison_{mob}.png"), dpi=120); plt.close(fig)
    print("wrote", a.out)

if __name__ == "__main__":
    main()
