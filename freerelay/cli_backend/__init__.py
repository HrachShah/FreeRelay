"""
FreeRelay — CLI Backend Module
================================
Spawns OpenCode CLI or Codex CLI as subprocesses and communicates via JSONL.

Usage:
    backend = CLIBackend("opencode")
    response = await backend.run("Explain how async/await works")

Supported backends:
- opencode-cli: Uses `opencode run --format json`
- codex-cli: Uses `codex run --format json`

Security: API keys are cleared from subprocess environment.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from freerelay.core.models.openai import (
    ChatCompletionResponse,
    Choice,
    Message,
    Usage,
)

logger = logging.getLogger("freerelay.cli_backend")

# Map backend names to their CLI commands
_BACKEND_COMMANDS: dict[str, list[str]] = {
    "opencode-cli": ["opencode", "run", "--format", "json"],
    "codex-cli": ["codex", "run", "--format", "json"],
}

# Environment variables to clear before spawning subprocess
_SENSITIVE_ENV_VARS = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_AI_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "TOGETHER_API_KEY",
        "MISTRAL_API_KEY",
        "NVIDIA_API_KEY",
        "OPENCODE_API_KEY",
        "OPENCODE_ZEN_API_KEY",
    }
)


@dataclass
class CLIBackendConfig:
    """Configuration for a CLI backend."""

    name: str
    command: list[str]
    cwd: str | None = None
    timeout_s: int = 120
    env_passthrough: list[str] = field(default_factory=list)


def _get_command(backend_name: str) -> list[str]:
    """Get the CLI command for a backend name."""
    cmd = _BACKEND_COMMANDS.get(backend_name)
    if cmd is None:
        raise ValueError(
            f"Unknown CLI backend: {backend_name}. "
            f"Available: {list(_BACKEND_COMMANDS.keys())}"
        )
    return list(cmd)


def _sanitize_env() -> dict[str, str]:
    """Create a clean environment for subprocess, removing API keys."""
    env = os.environ.copy()
    for key in _SENSITIVE_ENV_VARS:
        env.pop(key, None)
    return env


def _parse_codex_jsonl(line: str) -> str | None:
    """
    Parse a single JSONL line from Codex CLI output.

    Codex format: {"item": {"type": "message", "text": "..."}}
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    item = data.get("item", {})
    if item.get("type") == "message":
        return item.get("text")
    return None


def _parse_opencode_jsonl(line: str) -> str | None:
    """
    Parse a single JSONL line from OpenCode CLI output.

    OpenCode format: {"part": {"type": "text", "text": "..."}}
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    part = data.get("part", {})
    if part.get("type") == "text":
        return part.get("text")
    return None


_PARSERS: dict[str, Callable[[str], str | None]] = {
    "codex-cli": _parse_codex_jsonl,
    "opencode-cli": _parse_opencode_jsonl,
}


class CLIBackend:
    """
    Async wrapper for running OpenCode/Codex CLI as a subprocess.

    Communicates via JSONL over stdin/stdout.
    """

    def __init__(
        self,
        backend_name: str,
        cwd: str | None = None,
        timeout_s: int = 120,
    ) -> None:
        self.backend_name = backend_name
        self.command = _get_command(backend_name)
        self.cwd = cwd
        self.timeout_s = timeout_s
        self._parser = _PARSERS.get(backend_name, _parse_codex_jsonl)

    async def run(
        self,
        prompt: str,
        model: str | None = None,
        session_id: str | None = None,
    ) -> ChatCompletionResponse:
        """
        Run the CLI backend with a prompt and return a ChatCompletionResponse.

        Args:
            prompt: The user prompt to send.
            model: Optional model override (passed via --model flag).
            session_id: Optional session ID for continuity (passed via --session).

        Returns:
            ChatCompletionResponse in OpenAI format.
        """
        cmd = list(self.command)
        if model:
            cmd.extend(["--model", model])
        if session_id:
            cmd.extend(["--session", session_id])

        env = _sanitize_env()
        request_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        start_time = time.time()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self.cwd,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=prompt.encode("utf-8")),
                timeout=self.timeout_s,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            if proc.returncode != 0:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")[:500]
                logger.error(
                    "CLI backend %s failed (exit %d): %s",
                    self.backend_name,
                    proc.returncode,
                    stderr_text[:200],
                )
                return ChatCompletionResponse(
                    id=request_id,
                    created=int(time.time()),
                    model=f"cli/{self.backend_name}",
                    choices=[
                        Choice(
                            index=0,
                            message=Message(
                                role="assistant",
                                content=f"CLI backend error: {stderr_text[:200]}",
                            ),
                            finish_reason="stop",
                        )
                    ],
                )

            # Parse JSONL output
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            text_parts: list[str] = []
            for line in stdout_text.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                text = self._parser(line)
                if text:
                    text_parts.append(text)

            full_text = "".join(text_parts)

            logger.info(
                "CLI backend %s completed in %.0fms (%d chars)",
                self.backend_name,
                elapsed_ms,
                len(full_text),
            )

            return ChatCompletionResponse(
                id=request_id,
                created=int(time.time()),
                model=f"cli/{self.backend_name}",
                choices=[
                    Choice(
                        index=0,
                        message=Message(role="assistant", content=full_text),
                        finish_reason="stop",
                    )
                ],
                usage=Usage(
                    prompt_tokens=max(1, len(prompt) // 4),
                    completion_tokens=max(1, len(full_text) // 4),
                    total_tokens=max(1, (len(prompt) + len(full_text)) // 4),
                ),
            )

        except TimeoutError:
            logger.error(
                "CLI backend %s timed out after %ds",
                self.backend_name,
                self.timeout_s,
            )
            return ChatCompletionResponse(
                id=request_id,
                created=int(time.time()),
                model=f"cli/{self.backend_name}",
                choices=[
                    Choice(
                        index=0,
                        message=Message(
                            role="assistant",
                            content=f"CLI backend timed out after {self.timeout_s}s",
                        ),
                        finish_reason="stop",
                    )
                ],
            )

        except FileNotFoundError:
            logger.error(
                "CLI backend %s not found. Is %s installed?",
                self.backend_name,
                self.command[0],
            )
            return ChatCompletionResponse(
                id=request_id,
                created=int(time.time()),
                model=f"cli/{self.backend_name}",
                choices=[
                    Choice(
                        index=0,
                        message=Message(
                            role="assistant",
                            content=(
                                f"CLI '{self.command[0]}' not found. "
                                f"Install with: npm install -g {self.command[0]}"
                            ),
                        ),
                        finish_reason="stop",
                    )
                ],
            )

    async def stream_jsonl(
        self,
        prompt: str,
        model: str | None = None,
        session_id: str | None = None,
    ):
        """
        Stream output from CLI backend as JSONL lines.

        Yields parsed text chunks as they arrive.
        """
        cmd = list(self.command)
        if model:
            cmd.extend(["--model", model])
        if session_id:
            cmd.extend(["--session", session_id])

        env = _sanitize_env()

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=self.cwd,
        )

        # Send prompt
        proc.stdin.write(prompt.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()

        # Read stdout line by line
        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            text = self._parser(line)
            if text:
                yield text

        await proc.wait()


def list_available_backends() -> list[dict[str, str]]:
    """List all available CLI backends and their status."""
    import shutil

    backends = []
    for name, cmd in _BACKEND_COMMANDS.items():
        available = shutil.which(cmd[0]) is not None
        backends.append(
            {
                "name": name,
                "command": " ".join(cmd),
                "available": available,
                "install_hint": f"npm install -g {cmd[0]}",
            }
        )
    return backends


def get_backend_config() -> dict[str, object]:
    """Return CLI backend configuration for OpenClaw integration."""
    return {
        "cliBackends": [
            {
                "id": "codex-cli",
                "name": "Codex CLI",
                "command": ["codex", "run", "--format", "json"],
                "modelFlag": "--model",
                "sessionFlag": "--session",
                "outputParser": "parsed.item.text",
                "secure": True,
            },
            {
                "id": "opencode-cli",
                "name": "OpenCode CLI",
                "command": ["opencode", "run", "--format", "json"],
                "modelFlag": "--model",
                "sessionFlag": "--session",
                "outputParser": "parsed.part.text",
                "secure": True,
            },
        ]
    }
