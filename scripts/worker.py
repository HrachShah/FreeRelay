"""Blackbox AI codegen worker — chat-completions based.

Uses api.blackbox.ai/v1 with claude-opus-4.7 to generate bulk/boilerplate code.
Claude (the supervising session) reviews every output before saving.
See venture/RULES.md #6.

Usage:
    # one-shot generation
    python scripts/worker.py --prompt "Write a Python provider adapter for X"

    # from a file
    python scripts/worker.py --prompt-file prompts/phase1.txt

    # smoke test (costs ~1 token)
    python scripts/worker.py --smoke

    # pipe output to a file
    python scripts/worker.py --prompt "..." --out freerelay/providers/x.py

Env (loaded from .env):
    BLACKBOX_API_KEY   required
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

# ── config ─────────────────────────────────────────────────────────────────

def _load_env() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

BASE_URL = "https://api.blackbox.ai/v1"
API_KEY  = os.environ.get("BLACKBOX_API_KEY", "")
MODEL    = "blackboxai/anthropic/claude-opus-4.7"


SYSTEM = (
    "You are a senior Python engineer contributing to FreeRelay, a self-hosted "
    "AI gateway (FastAPI, Python 3.12). Output only valid Python code unless "
    "explicitly asked for prose. No markdown fences, no preamble."
)

# ── core ──────────────────────────────────────────────────────────────────

def complete(prompt: str, system: str = SYSTEM, max_tokens: int = 4096) -> str:
    if not API_KEY:
        sys.exit("BLACKBOX_API_KEY not set in .env")

    messages = [{"role": "user", "content": prompt}]
    resp = httpx.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "max_tokens": max_tokens,
              "system": system},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Blackbox codegen worker for FreeRelay")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--prompt",      metavar="TEXT")
    g.add_argument("--prompt-file", metavar="PATH", type=Path)
    g.add_argument("--smoke",       action="store_true",
                   help="Smoke test — one short call to verify the key works")
    ap.add_argument("--out", metavar="PATH", type=Path,
                    help="Write output to this file instead of stdout")
    ap.add_argument("--max-tokens", type=int, default=4096)
    args = ap.parse_args()

    if args.smoke:
        result = complete("Reply with exactly: WORKER ONLINE", max_tokens=10)
        print(result)
        return

    prompt = args.prompt or args.prompt_file.read_text(encoding="utf-8")
    result = complete(prompt, max_tokens=args.max_tokens)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result, encoding="utf-8")
        print(f"Written to {args.out}")
    else:
        print(result)


if __name__ == "__main__":
    main()
