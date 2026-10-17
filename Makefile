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
MAX_USD ?= 45
RUN ?= v4

.PHONY: reproduce install test april smoke provenance estimate run run-heldout run-dev run-bid analyze

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
	rm -rf runs_private/smoke results/smoke
	$(BIN)/python -m evals.run_constitutional --name smoke --targets fake-target --judges fake-judge,fake-judge-2 --samples 2 --limit 4
	$(BIN)/python -m analysis.analyze_constitutional --run runs_private/smoke --out results/smoke/constitutional
	$(BIN)/python -m evals.run_bid_cot --name smoke-bid --targets fake-target --judges fake-judge,fake-judge-2 --limit 4
	$(BIN)/python -m analysis.analyze_bid_cot --run runs_private/smoke-bid --out results/smoke/bid_cot
	rm -rf runs_private/smoke-bid

provenance:
	$(BIN)/python scripts/provenance.py > results/PROVENANCE.json

estimate:
	$(BIN)/python scripts/estimate.py --experiment constitutional --judges $(JUDGES) --samples 3
	$(BIN)/python scripts/estimate.py --experiment constitutional --judges $(JUDGE1) --samples 1
	$(BIN)/python scripts/estimate.py --experiment bid_cot --judges $(JUDGES) --samples 2

# --- paid runs (pre-registered; see PREREGISTRATION.md). Resumable: re-run the same command after any interruption.
run: run-heldout run-dev run-bid analyze provenance

run-heldout:
	$(BIN)/python -m evals.run_constitutional --name $(RUN)-heldout --splits heldout --samples 3 --targets $(TARGET) --judges $(JUDGES) --max-usd $(MAX_USD)

run-dev:
	$(BIN)/python -m evals.run_constitutional --name $(RUN)-dev --splits dev --samples 1 --targets $(TARGET) --judges $(JUDGE1) --max-usd 10

run-bid:
	$(BIN)/python -m evals.run_bid_cot --name $(RUN)-bid --samples 2 --targets $(TARGET) --judges $(JUDGES) --max-usd 15

analyze:
	$(BIN)/python -m analysis.analyze_constitutional --run runs_private/$(RUN)-heldout --out results/constitutional_v4/heldout
	$(BIN)/python -m analysis.analyze_constitutional --run runs_private/$(RUN)-dev --out results/constitutional_v4/dev
	$(BIN)/python -m analysis.analyze_bid_cot --run runs_private/$(RUN)-bid --out results/bid_cot_v2
	for d in $(RUN)-heldout $(RUN)-dev $(RUN)-bid; do mkdir -p results/manifests && cp runs_private/$$d/manifest.json results/manifests/$$d.json && cp runs_private/$$d/spend.jsonl results/manifests/$$d.spend.jsonl; done
