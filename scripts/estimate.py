"""Rough cost estimate before a paid run (token counts are approximations; the budget guard uses real usage)."""
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from evals.common import price

TOK = {"const_in": 120, "const_out": 350, "cjudge_in": 1250, "cjudge_out": 90,
       "bid_in": 90, "bid_out": 550, "rubric_in": 900, "rubric_out": 250, "transfer_in": 850, "transfer_out": 70, "pair_in": 1400, "pair_out": 60}


def usd(m, i, o):
    p = price(m); return (i * p["input"] + o * p["output"]) / 1e6


ap = argparse.ArgumentParser()
ap.add_argument("--experiment", choices=["constitutional", "bid_cot"], required=True)
ap.add_argument("--targets", default="claude-haiku-4-5"); ap.add_argument("--judges", default="claude-sonnet-4-6")
ap.add_argument("--prompts", type=int, default=50); ap.add_argument("--samples", type=int, default=3)
ap.add_argument("--conditions", type=int, default=3)
a = ap.parse_args()
T, J = a.targets.split(","), a.judges.split(",")
total, lines = 0.0, []
if a.experiment == "constitutional":
    n = a.prompts * a.conditions * a.samples
    for t in T:
        c = n * usd(t, TOK["const_in"], TOK["const_out"]); total += c; lines.append(f"  target {t}: {n} responses ~ ${c:.2f}")
    for j in J:
        k = n * len(T) * 4 + 40
        c = k * usd(j, TOK["cjudge_in"], TOK["cjudge_out"]); total += c; lines.append(f"  judge  {j}: {k} calls ~ ${c:.2f}")
else:
    n = 30 * 3 * a.samples
    for t in T:
        c = n * usd(t, TOK["bid_in"], TOK["bid_out"]); total += c; lines.append(f"  target {t}: {n} answers ~ ${c:.2f}")
    for j in J:
        k1, k2 = n * len(T), 30 * a.samples * 2 * len(T)
        c = k1 * (usd(j, TOK["rubric_in"], TOK["rubric_out"]) + usd(j, TOK["transfer_in"], TOK["transfer_out"])) + k2 * usd(j, TOK["pair_in"], TOK["pair_out"])
        total += c; lines.append(f"  judge  {j}: {2 * k1 + k2} calls ~ ${c:.2f}")
print(f"Estimate ({a.experiment}):"); print("\n".join(lines)); print(f"  TOTAL ~ ${total:.2f} (prices from config/pricing.json; verify them)")
