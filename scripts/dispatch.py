"""Blackbox Agent API dispatcher — submits tasks against HrachShah/FreeRelay.

Worker model: blackboxai/anthropic/claude-opus-4.8
Blackbox generates code; Claude reviews the resulting branch before merge.
See venture/RULES.md #6.

Usage:
    python scripts/dispatch.py --task "Add X to freerelay/providers/"
    python scripts/dispatch.py --task "..." --dry-run   # print payload, don't submit
    python scripts/dispatch.py --poll <task-id>         # poll an existing task for status

Env:
    BLACKBOX_API_KEY   required (never hardcode — see .env)
    FREERELAY_REPO     override repo URL (default: https://github.com/HrachShah/FreeRelay.git)

# ponytail: no retries/backoff here yet — add if Blackbox has flaky task creation
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

# ── config ──────────────────────────────────────────────────────────────────

def _load_env() -> None:
    """Load .env from repo root (if present) without requiring python-dotenv."""
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

API_BASE      = "https://agent.blackbox.ai/api/v1"
API_KEY       = os.environ.get("BLACKBOX_API_KEY", "")
REPO_URL      = os.environ.get("FREERELAY_REPO", "https://github.com/HrachShah/FreeRelay.git")
WORKER_MODEL  = "blackboxai/anthropic/claude-opus-4.8"
POLL_INTERVAL = 10   # seconds between status polls
POLL_TIMEOUT  = 900  # 15 min max wait

# ── core ─────────────────────────────────────────────────────────────────────

def _headers() -> dict[str, str]:
    if not API_KEY:
        sys.exit("BLACKBOX_API_KEY not set. Add it to .env or export it.")
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _task_payload(prompt: str) -> dict:
    return {
        "prompt":   prompt,
        "model":    WORKER_MODEL,
        "agent":    "claude",
        "repoUrl":  REPO_URL,
    }


def submit(prompt: str, dry_run: bool = False) -> str | None:
    """Submit a task. Returns task_id, or None on --dry-run."""
    payload = _task_payload(prompt)
    if dry_run:
        print("-- DRY RUN (not submitted) --------------------------")
        print(f"POST {API_BASE}/tasks")
        print(json.dumps(payload, indent=2))
        return None

    with httpx.Client(timeout=30) as client:
        resp = client.post(f"{API_BASE}/tasks", headers=_headers(), json=payload)
    resp.raise_for_status()
    data = resp.json()
    task_id = data.get("id") or data.get("task_id") or data.get("taskId")
    if not task_id:
        print(f"Unexpected response shape — raw:\n{json.dumps(data, indent=2)}")
        sys.exit(1)
    print(f"Task submitted: {task_id}")
    return task_id


def poll(task_id: str) -> dict:
    """Poll until terminal state; return the final task object."""
    deadline = time.monotonic() + POLL_TIMEOUT
    terminal = {"completed", "failed", "error", "cancelled", "done", "success"}

    with httpx.Client(timeout=15) as client:
        while True:
            resp = client.get(
                f"{API_BASE}/tasks/{task_id}",
                headers=_headers(),
            )
            # 404 might mean the endpoint is /task (singular) — try it
            if resp.status_code == 404:
                resp = client.get(f"{API_BASE}/task/{task_id}", headers=_headers())
            resp.raise_for_status()
            data = resp.json()

            status = (data.get("status") or "").lower()
            print(f"  [{status}] {task_id}", end="\r", flush=True)

            if status in terminal:
                print()  # newline after \r
                return data

            if time.monotonic() > deadline:
                sys.exit(f"Timed out after {POLL_TIMEOUT}s — last status: {status}")

            time.sleep(POLL_INTERVAL)


def run(prompt: str, dry_run: bool = False) -> None:
    """Submit + poll; print the result summary."""
    task_id = submit(prompt, dry_run=dry_run)
    if task_id is None:
        return

    print(f"Polling every {POLL_INTERVAL}s (max {POLL_TIMEOUT}s)…")
    result = poll(task_id)
    print("\n-- Result -------------------------------------------")
    print(json.dumps(result, indent=2))

    # Probe: capture what fields actually came back so we can harden the contract
    known_fields = {"status", "branch", "pr", "pullRequest", "patch", "output", "error"}
    found = {k for k in result if k in known_fields}
    print(f"\nFields present: {found}")
    if not found:
        print("⚠ Unknown response shape — log result above and update dispatch.py contract.")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Dispatch a Blackbox agent task against FreeRelay")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--task",  metavar="PROMPT", help="Task prompt to submit")
    g.add_argument("--poll",  metavar="TASK_ID", help="Poll an existing task by ID")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print payload without submitting (zero credits burned)")
    args = ap.parse_args()

    if args.poll:
        result = poll(args.poll)
        print(json.dumps(result, indent=2))
    else:
        run(args.task, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
