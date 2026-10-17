"""Apply the pre-registered rule for the second judge (PREREGISTRATION.md, section 2) and print the model id.

Rule: if OPENAI_API_KEY is set, the most recently created OpenAI model whose id starts with "gpt-" and is a full-size
text model (id contains none of the excluded words below); otherwise the most recently created Claude Opus model.
"""
import os, sys

EXCLUDE = ("mini", "nano", "audio", "realtime", "search", "transcribe", "tts", "image", "codex", "chat-latest", "oss", "instruct")


def pick():
    if os.environ.get("OPENAI_API_KEY"):
        import openai
        ms = [m for m in openai.OpenAI().models.list() if m.id.startswith("gpt-") and not any(x in m.id for x in EXCLUDE)]
        if ms:
            return max(ms, key=lambda m: m.created).id, "openai (cross-family)"
    import anthropic
    ms = [m for m in anthropic.Anthropic().models.list(limit=100) if m.id.startswith("claude-opus")]
    if not ms:
        sys.exit("No Claude Opus model listed for this API key.")
    return max(ms, key=lambda m: m.created_at).id, "anthropic (same family as the primary judge)"


if __name__ == "__main__":
    mid, why = pick()
    print(mid)
    print(f"second judge: {mid} [{why}]", file=sys.stderr)
