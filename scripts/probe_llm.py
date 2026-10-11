"""Live smoke test of both LLM engines (run before every deploy; never in CI).

Per engine: one plain chat call and one forced tool call, both through the same request options
the gateway uses (``max_completion_tokens`` and the engine's provider extras). Prints the engine
alias, latency and outcome only; secrets are never printed.

Usage (from the repo root):
    backend\\.venv\\Scripts\\python.exe scripts\\probe_llm.py [--engine primary|backup] [--vision]
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.agent.engines import engines, make_client, request_options  # noqa: E402
from app.config import get_settings  # noqa: E402

TOOL = {
    "type": "function",
    "function": {
        "name": "report_status",
        "description": "Report a short status word.",
        "parameters": {
            "type": "object",
            "properties": {"status": {"type": "string", "description": "One word."}},
            "required": ["status"],
        },
    },
}


def _tiny_png() -> str:
    """A 32x32 red PNG (the primary rejects images under 32 px), built in memory, as a data URL."""
    size = 32
    raw = (b"\x00" + b"\xff\x00\x00" * size) * size

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return len(data).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big")

    header = size.to_bytes(4, "big") * 2 + b"\x08\x02\x00\x00\x00"
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _call(engine, label: str, **kwargs) -> bool:  # type: ignore[no-untyped-def]
    client = make_client(engine)
    started = time.perf_counter()
    try:
        res = client.chat.completions.create(
            model=engine.model, **request_options(engine, max_completion_tokens=512), **kwargs)
    except Exception as exc:  # noqa: BLE001 - a probe reports every failure the same way
        ms = int((time.perf_counter() - started) * 1000)
        print(f"  {label:<10} FAIL  {ms:>6} ms  {type(exc).__name__}: {str(exc)[:200]}")
        return False
    ms = int((time.perf_counter() - started) * 1000)
    choice = res.choices[0]
    calls = choice.message.tool_calls or []
    detail = (f"tool={calls[0].function.name} args={calls[0].function.arguments}" if calls
              else f"content={(choice.message.content or '')[:60]!r}")
    print(f"  {label:<10} OK    {ms:>6} ms  finish={choice.finish_reason} {detail}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=("primary", "backup"))
    parser.add_argument("--vision", action="store_true", help="also send a tiny image")
    args = parser.parse_args()
    settings = get_settings()
    ok = True
    for engine in engines(settings):
        if args.engine and engine.alias != args.engine:
            continue
        print(f"{engine.alias}:")
        if not engine.configured:
            print("  not configured (no API key)")
            ok = False
            continue
        ok &= _call(engine, "chat", messages=[{"role": "user", "content": "Reply with OK."}])
        ok &= _call(engine, "tool", messages=[{"role": "user", "content": "Report status ok."}],
                    tools=[TOOL],
                    tool_choice={"type": "function", "function": {"name": "report_status"}})
        if args.vision:
            ok &= _call(engine, "vision", response_format={"type": "json_object"}, messages=[{
                "role": "user", "content": [
                    {"type": "text", "text": 'Return JSON {"colour": "<main colour>"}.'},
                    {"type": "image_url", "image_url": {"url": _tiny_png()}},
                ]}])
    print(json.dumps({"ok": bool(ok)}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
