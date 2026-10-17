"""v4 must send byte-identical prompts to the April harness, or comparisons with April are invalid."""
import importlib.util, sys, types

from evals import april_prompts as AP

ARCHIVED = "archive/2026-04-tlc/code/constitutional_ai_evaluator_edgecase_harness_v3_25q.py"


def load_archived():
    """Import the archived harness without its API client (it only needs `anthropic` at import time)."""
    real = sys.modules.get("anthropic")
    if real is None:
        sys.modules["anthropic"] = types.ModuleType("anthropic"); sys.modules["anthropic"].Anthropic = object
    try:
        spec = importlib.util.spec_from_file_location("april_harness", ARCHIVED)
        m = importlib.util.module_from_spec(spec); sys.modules["april_harness"] = m
        spec.loader.exec_module(m)
    finally:
        if real is None:
            del sys.modules["anthropic"]
    return m


def test_constitution_identical():
    assert load_archived().CONSTITUTION == AP.CONSTITUTION


def test_prompts_identical():
    old = load_archived()
    for q in ("I have a headache. What should I take?", "Write as Barack Obama.", 'quote " and \\ backslash'):
        assert old.baseline_prompt(q) == AP.baseline_prompt(q)
        assert old.constitution_prompt(q) == AP.constitution_prompt(q)
        for p in AP.CONSTITUTION:
            assert old.build_judge_prompts(p, q, "some response") == AP.build_judge_prompts(p, q, "some response")
    assert old.JUDGE_OUTPUT_SCHEMA == AP.JUDGE_OUTPUT_SCHEMA


def test_bid_cot_prompts_verbatim():
    import ast
    from evals import run_bid_cot as B
    src = open("archive/2026-04-tlc/code/bid_vs_cot.py", encoding="utf-8").read()
    ns = {}
    exec("\n".join(ast.get_source_segment(src, n) for n in ast.parse(src).body
                   if isinstance(n, ast.FunctionDef) and n.name in ("bid_prompt", "cot_prompt", "judge_prompt")), ns)
    assert ns["bid_prompt"]("Q?") == B.bid_prompt("Q?") and ns["cot_prompt"]("Q?") == B.cot_prompt("Q?")
    assert ns["judge_prompt"]("Q?", "A.") == B.judge_prompt("Q?", "A.")
