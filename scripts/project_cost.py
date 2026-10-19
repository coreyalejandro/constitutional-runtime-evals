"""Project the cost of the pre-registered runs from MEASURED usage in a pilot run (Amendment 1).

The pilot sends a handful of real calls per model; this script averages the settled cost per call for each
model and multiplies by the number of calls each planned stage needs. Pilot outputs are used only for this
projection and are never analysed.

Usage: python3 scripts/project_cost.py --ledger runs_private/SPEND.jsonl --pilot-run pilot --judges J1,J2 [--cap 36]
Exit code 4 if the projection for the required stages is above --cap.
"""
import argparse, json, os, sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from evals.common import load_jsonl

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default="runs_private/SPEND.jsonl"); ap.add_argument("--pilot-run", default="pilot")
ap.add_argument("--target", default="claude-haiku-4-5"); ap.add_argument("--judges", required=True)
ap.add_argument("--cap", type=float, default=36.0)
a = ap.parse_args()
J = a.judges.split(",")
per = defaultdict(list)
for r in load_jsonl(a.ledger, quarantine=False):
    if r.get("run") == a.pilot_run and r.get("type") in ("settled", "charged_unknown"):
        per[r["model"]].append(r["usd"])
missing = [m for m in [a.target] + J if not per.get(m)]
if missing:
    sys.exit(f"No pilot calls recorded for {missing}; run the pilot first.")
avg = {m: sum(v) / len(v) for m, v in per.items()}
stages = {
    "heldout (required)": {a.target: 50 * 3 * 3, **{j: 50 * 3 * 3 * 4 + 40 for j in J}},
    "bid (required)": {a.target: 30 * 3 * 2, **{j: 30 * 3 * 2 * 2 + 30 * 2 * 2 for j in J}},
    "dev replication (optional)": {a.target: 50 * 3 * 1, J[0]: 50 * 3 * 1 * 4 + 40},
}
out, total_req = {}, 0.0
for s, calls in stages.items():
    usd = sum(n * avg[m] for m, n in calls.items())
    out[s] = round(usd, 2)
    if "required" in s:
        total_req += usd
print(json.dumps({"avg_usd_per_call": {m: round(v, 5) for m, v in avg.items()}, "pilot_calls": {m: len(v) for m, v in per.items()},
                  "projected_usd": out, "required_total": round(total_req, 2), "cap": a.cap}, indent=2))
if total_req > a.cap:
    print(f"STOP: required stages project to ${total_req:.2f}, above the ${a.cap:.2f} cap. Ask the owner before running.")
    sys.exit(4)
print("OK: projection is within the cap.")
