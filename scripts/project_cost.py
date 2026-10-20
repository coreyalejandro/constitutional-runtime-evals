"""Project the cost of the pre-registered runs from MEASURED usage in two pilots (Amendments 1 and 2).

Pilots: 'pilot' (constitutional: responses + judgments) and 'pilot-bid' (BID vs CoT: answers + rubric, transfer and
pairwise judging). Every ledger row carries the call kind, so each kind of call is projected from its own measured cost.
The projection is CONSERVATIVE: it uses the most expensive observed call of each (model, kind), not the average.
Probe calls use the judgment cost (same prompt template). Pilot outputs are never analysed.

Usage: python3 scripts/project_cost.py --ledger runs_private/SPEND.jsonl --target T --judges J1,J2 [--cap 36]
Exit code 4 if the required stages project above --cap; exit 5 if a needed (model, kind) was not measured.
"""
import argparse, json, os, sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from evals.common import load_jsonl

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default="runs_private/SPEND.jsonl")
ap.add_argument("--pilot-runs", default="pilot,pilot-bid")
ap.add_argument("--target", default="claude-haiku-4-5"); ap.add_argument("--judges", required=True)
ap.add_argument("--cap", type=float, default=36.0)
a = ap.parse_args()
J = a.judges.split(",")
pilots = set(a.pilot_runs.split(","))
per = defaultdict(list)
spent_so_far = 0.0
for r in load_jsonl(a.ledger, quarantine=False):
    if r.get("type") in ("settled", "charged_unknown"):
        spent_so_far += r["usd"]
        if r.get("run") in pilots:
            per[(r["model"], r.get("kind"))].append(r["usd"])
cost = {k: max(v) for k, v in per.items()}
cost.update({(m, "probe"): c for (m, k), c in list(cost.items()) if k == "judgment" and (m, "probe") not in cost})

stages = {
    "heldout (required)": [(a.target, "response", 50 * 3 * 3)] + [(j, "judgment", 50 * 3 * 3 * 4) for j in J] + [(j, "probe", 40) for j in J],
    "bid (required)": [(a.target, "answer", 30 * 3 * 2)] + [(j, k, 30 * 3 * 2) for j in J for k in ("rubric", "transfer")]
                      + [(j, "pairwise", 30 * 2 * 2) for j in J],
    "dev replication (optional)": [(a.target, "response", 50 * 3 * 1), (J[0], "judgment", 50 * 3 * 1 * 4), (J[0], "probe", 40)],
}
missing = sorted({(m, k) for s in stages.values() for m, k, _ in s if (m, k) not in cost})
if missing:
    print(f"STOP: no pilot measurement for {missing}. Run both pilots first.")
    sys.exit(5)
out, total_req = {}, 0.0
for s, items in stages.items():
    usd = sum(n * cost[(m, k)] for m, k, n in items)
    out[s] = round(usd, 2)
    if "required" in s:
        total_req += usd
need = spent_so_far + total_req
print(json.dumps({"max_observed_usd_per_call": {f"{m}|{k}": round(v, 5) for (m, k), v in sorted(cost.items())},
                  "pilot_calls": {f"{m}|{k}": len(v) for (m, k), v in sorted(per.items())},
                  "projected_usd": out, "required_total": round(total_req, 2), "already_spent": round(spent_so_far, 4),
                  "spent_plus_required": round(need, 2), "cap": a.cap}, indent=2))
if need > a.cap:
    print(f"STOP: already spent ${spent_so_far:.2f} + required stages ${total_req:.2f} = ${need:.2f}, above the ${a.cap:.2f} cap. "
          f"Ask the owner before running.")
    sys.exit(4)
print("OK: conservative projection is within the cap.")
