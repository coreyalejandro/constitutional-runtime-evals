# Constitutional runtime evals: one-command reproduction.
#   make reproduce   -> offline: tests, April re-analysis, fake end-to-end pipeline, provenance (no API key, no cost)
#   make estimate    -> cost estimate for the pre-registered paid runs
#   make run         -> the pre-registered paid runs (needs ANTHROPIC_API_KEY; optional OPENAI_API_KEY)
#   make analyze     -> public, redacted results from runs_private/
PY ?= python3
VENV := .venv
BIN := $(VENV)/bin
TARGET ?= claude-haiku-4-5
JUDGE1 ?= claude-sonnet-4-6
JUDGE2 ?=
comma := ,
JUDGES = $(JUDGE1)$(if $(JUDGE2),$(comma)$(JUDGE2))
RUN ?= v4

.PHONY: reproduce install test april smoke provenance estimate need-judge2 pilot run run-heldout run-dev run-bid analyze

reproduce: install test april smoke provenance
	@echo "Done. April re-analysis: results/APRIL_REANALYSIS.md. Pipeline smoke test (fake model): results/smoke/."

install:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q -r requirements.txt

test:
	$(BIN)/python -m pytest -q -p no:cacheprovider tests --junitxml=results/junit.xml

april:
	$(BIN)/python -m analysis.reanalyze_april

smoke:
	rm -rf runs_private/smoke runs_private/smoke-bid results/smoke
	$(BIN)/python -m evals.run_constitutional --name smoke --targets fake-target --judges fake-judge,fake-judge-2 --samples 2 --limit 4 --ledger runs_private/smoke/SPEND.jsonl
	$(BIN)/python -m analysis.analyze_constitutional --run runs_private/smoke --out results/smoke/constitutional
	$(BIN)/python -m evals.run_bid_cot --name smoke-bid --targets fake-target --judges fake-judge,fake-judge-2 --limit 4 --ledger runs_private/smoke/SPEND.jsonl
	$(BIN)/python -m analysis.analyze_bid_cot --run runs_private/smoke-bid --out results/smoke/bid_cot
	rm -rf runs_private/smoke-bid

provenance:
	$(BIN)/python scripts/provenance.py > results/PROVENANCE.json

estimate:
	$(BIN)/python scripts/estimate.py --experiment constitutional --judges $(JUDGES) --samples 3
	$(BIN)/python scripts/estimate.py --experiment constitutional --judges $(JUDGE1) --samples 1
	$(BIN)/python scripts/estimate.py --experiment bid_cot --judges $(JUDGES) --samples 2

# --- paid runs (pre-registered + Amendment 1). Resumable. ONE shared ledger and ONE cap for all stages.
# The provider-side hard limit is the prepaid credit balance with auto-reload off; MAX_USD is a local guard below it.
MAX_USD ?= 36
LEDGER := runs_private/SPEND.jsonl
PAID = --max-usd $(MAX_USD) --ledger $(LEDGER)

need-judge2:
	@test -n "$(JUDGE2)" || (echo "JUDGE2 is required for the registered run (two judges). Example: make run JUDGE2=claude-opus-5-5" && exit 1)

pilot: need-judge2
	$(BIN)/python -m evals.run_constitutional --name pilot --splits heldout --limit 1 --samples 1 --conditions baseline,constitution --no-probes --targets $(TARGET) --judges $(JUDGES) --require-judges 2 $(PAID) || true
	$(BIN)/python -m evals.run_bid_cot --name pilot-bid --limit 1 --samples 1 --targets $(TARGET) --judges $(JUDGES) --require-judges 2 $(PAID) || true
	$(BIN)/python scripts/project_cost.py --ledger $(LEDGER) --target $(TARGET) --judges $(JUDGES) --cap $(MAX_USD)

run: pilot run-heldout run-bid run-dev analyze provenance

run-heldout: need-judge2
	$(BIN)/python -m evals.run_constitutional --name $(RUN)-heldout --splits heldout --samples 3 --targets $(TARGET) --judges $(JUDGES) --require-judges 2 $(PAID)

run-bid: need-judge2
	$(BIN)/python -m evals.run_bid_cot --name $(RUN)-bid --samples 2 --targets $(TARGET) --judges $(JUDGES) --require-judges 2 $(PAID)

run-dev:
	$(BIN)/python -m evals.run_constitutional --name $(RUN)-dev --splits dev --samples 1 --targets $(TARGET) --judges $(JUDGE1) $(PAID) || echo "Dev replication stopped (optional stage; see completion.json)."

analyze:
	$(BIN)/python -m analysis.analyze_constitutional --run runs_private/$(RUN)-heldout --out results/constitutional_v4/heldout
	test -d runs_private/$(RUN)-dev && $(BIN)/python -m analysis.analyze_constitutional --run runs_private/$(RUN)-dev --out results/constitutional_v4/dev || echo "No dev replication to analyse."
	$(BIN)/python -m analysis.analyze_bid_cot --run runs_private/$(RUN)-bid --out results/bid_cot_v2
	mkdir -p results/manifests && for d in $(RUN)-heldout $(RUN)-dev $(RUN)-bid pilot pilot-bid; do test -d runs_private/$$d && cp runs_private/$$d/manifest.json results/manifests/$$d.manifest.json && cp runs_private/$$d/completion.json results/manifests/$$d.completion.json || true; done
	cp $(LEDGER) results/manifests/SPEND.jsonl
