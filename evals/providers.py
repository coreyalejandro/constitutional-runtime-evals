"""Model providers behind one small interface.

complete(model, system, user, max_tokens, temperature, json_schema=None) -> Completion

API keys are read from the environment only (ANTHROPIC_API_KEY, OPENAI_API_KEY) by the active harness.
Error text is passed through evals.common.sanitize() before it is returned, so anything shaped like a key
is removed before it can reach a log or result file.

Retries: a request is re-sent here only when the provider REJECTED it without processing it (HTTP 429, 503,
529), which is not billed. Timeouts and connection errors are NOT retried here, because a timed-out request
can still be billed; the runner retries those as new attempts, each with its own budget reservation.
"""
from __future__ import annotations

import hashlib, json, os, random, time

from evals.common import sanitize
from dataclasses import dataclass, asdict


@dataclass
class Completion:
    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    error: str | None = None
    attempts: int = 1
    temperature_applied: bool | None = None

    def to_dict(self):
        return asdict(self)


_UNBILLED_REJECTIONS = (429, 503, 529)


class SendError(Exception):
    def __init__(self, err, sends):
        super().__init__(str(err))
        self.err, self.sends = err, sends


def _retry(fn, tries=8):
    """Returns (response, sends). Raises SendError(original exception, sends) on failure."""
    sends = 0
    for a in range(tries):
        sends += 1
        try:
            return fn(), sends
        except Exception as e:
            if getattr(e, "status_code", None) in _UNBILLED_REJECTIONS and a < tries - 1:
                time.sleep(min(60, 2 ** a + random.random()))
                continue
            raise SendError(e, sends)
    raise SendError(RuntimeError("retries exhausted"), sends)


def _err(e):
    inner = e.err if isinstance(e, SendError) else e
    return sanitize(f"{type(inner).__name__}: {str(inner)[:300]}")


def _sends(e):
    return e.sends if isinstance(e, SendError) else 1


class AnthropicProvider:
    family = "anthropic"

    def __init__(self):
        import anthropic
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set in the environment.")
        self.client = anthropic.Anthropic(max_retries=0, timeout=120)

    def list_models(self):
        try:
            return sorted(m.id for m in self.client.models.list(limit=100))
        except Exception as e:
            return [f"<list failed: {type(e).__name__}>"]  # resolve_models() fails closed on this

    def complete(self, model, system, user, max_tokens, temperature, json_schema=None):
        kw = dict(model=model, system=system, messages=[{"role": "user", "content": user}], max_tokens=max_tokens)
        if json_schema is not None:
            kw["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
        applied = None
        if temperature is not None:  # SDK 1.x dropped the typed argument; the API decides per model
            kw["extra_body"] = {"temperature": temperature}; applied = True
        try:
            r, n = _retry(lambda: self.client.messages.create(**kw))
        except SendError as e:
            if applied and "temperature" in str(e.err).lower() and getattr(e.err, "status_code", None) == 400:
                kw.pop("extra_body"); applied = False
                try:
                    r, n2 = _retry(lambda: self.client.messages.create(**kw)); n = e.sends + n2
                except SendError as e2:
                    return Completion("", None, 0, 0, _err(e2), e.sends + e2.sends)
            else:
                return Completion("", None, 0, 0, _err(e), e.sends)
        text = "\n".join(b.text for b in r.content if getattr(b, "type", None) == "text").strip()
        return Completion(text, r.stop_reason, r.usage.input_tokens, r.usage.output_tokens, None, n, applied)


class OpenAIProvider:
    family = "openai"

    def __init__(self):
        import openai
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is not set in the environment.")
        self.client = openai.OpenAI(max_retries=0, timeout=120)

    def list_models(self):
        try:
            return sorted(m.id for m in self.client.models.list())
        except Exception as e:
            return [f"<list failed: {type(e).__name__}>"]  # resolve_models() fails closed on this

    def complete(self, model, system, user, max_tokens, temperature, json_schema=None):
        kw = dict(model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                  max_completion_tokens=max_tokens)
        applied = None
        if temperature is not None:
            kw["temperature"] = temperature; applied = True
        if json_schema is not None:
            kw["response_format"] = {"type": "json_schema", "json_schema": {"name": "judgment", "schema": json_schema, "strict": True}}
        try:
            r, n = _retry(lambda: self.client.chat.completions.create(**kw))
        except SendError as e:
            if "temperature" in str(e.err).lower() and "temperature" in kw and getattr(e.err, "status_code", None) == 400:
                kw.pop("temperature"); applied = False  # some reasoning models fix temperature
                try:
                    r, n2 = _retry(lambda: self.client.chat.completions.create(**kw)); n = e.sends + n2
                except SendError as e2:
                    return Completion("", None, 0, 0, _err(e2), e.sends + e2.sends)
            else:
                return Completion("", None, 0, 0, _err(e), e.sends)
        c = r.choices[0]
        return Completion((c.message.content or "").strip(), c.finish_reason, r.usage.prompt_tokens, r.usage.completion_tokens, None, n, applied)


class FakeProvider:
    """Deterministic stand-in for tests and CI. Output is labelled FAKE and is never a result."""
    family = "fake"

    def list_models(self):
        return ["fake-judge", "fake-judge-2", "fake-target"]

    def complete(self, model, system, user, max_tokens, temperature, json_schema=None):
        h = int(hashlib.sha256((model + system + user).encode()).hexdigest(), 16)
        if json_schema is not None:
            props = json_schema.get("properties", {})
            if "score" in props:
                s = 1 + h % 5
                out = {"score": s, "justification": "FAKE judgment.", "violation": s <= 2}
            elif "preferred" in props:
                out = {"preferred": ["A", "B", "tie"][h % 3], "justification": "FAKE."}
            else:
                out = {k: 1 + (h >> (4 * i)) % 5 for i, k in enumerate(props) if props[k].get("type") == "integer"}
                out.update({k: "FAKE." for k in props if props[k].get("type") == "string"})
            text = json.dumps(out)
        else:
            text = f"FAKE response {h % 10_000} " + "lorem " * (h % 50)
        return Completion(text, "end_turn", len(system + user) // 4, len(text) // 4)


def family_of(model: str) -> str:
    if model.startswith("fake"):
        return "fake"
    if model.startswith(("gpt", "o1", "o3", "o4", "o5")):
        return "openai"
    return "anthropic"


_CLASSES = {"fake": FakeProvider, "openai": OpenAIProvider, "anthropic": AnthropicProvider}


def providers_for(models):
    """One provider instance per family; returns ({family: provider}, {model: provider})."""
    fams = {}
    for m in models:
        f = family_of(m)
        if f not in fams:
            fams[f] = _CLASSES[f]()
    return fams, {m: fams[family_of(m)] for m in models}
