"""
FreeRelay — Skills Integration
================================
Dedicated skills that let FreeRelay/OpenClaw invoke OpenCode and Codex
as agent skills, plus a coding-supervisor skill for monitoring.

Skills:
- opencode: Invoke OpenCode CLI for coding tasks
- codex: Invoke Codex CLI for coding tasks
- coding-supervisor: Monitor and supervise AI coding sessions
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("freerelay.skills")


class SkillStatus(StrEnum):
    """Skill execution status."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class SkillResult:
    """Result of a skill execution."""

    skill_id: str
    status: SkillStatus
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillDefinition:
    """Defines an available skill."""

    id: str
    name: str
    description: str
    command: list[str]
    supports_streaming: bool = False
    supports_session: bool = False
    category: str = "coding"


# Built-in skill definitions
SKILL_DEFINITIONS: dict[str, SkillDefinition] = {
    "opencode": SkillDefinition(
        id="opencode",
        name="OpenCode",
        description=(
            "Invoke OpenCode CLI for coding tasks. "
            "Supports Claude, GPT, Gemini, Kimi, GLM, MiniMax."
        ),
        command=["opencode", "run", "--format", "json"],
        supports_streaming=True,
        supports_session=True,
        category="coding",
    ),
    "codex": SkillDefinition(
        id="codex",
        name="Codex",
        description="Invoke Codex CLI for coding tasks. Uses OpenAI Codex models.",
        command=["codex", "run", "--format", "json"],
        supports_streaming=True,
        supports_session=True,
        category="coding",
    ),
    "coding-supervisor": SkillDefinition(
        id="coding-supervisor",
        name="Coding Supervisor",
        description=(
            "Monitor and supervise AI coding sessions. "
            "Reviews code changes, validates tests, provides feedback."
        ),
        command=[],  # In-process skill, no subprocess
        supports_streaming=False,
        supports_session=False,
        category="supervision",
    ),
}


def get_skill(skill_id: str) -> SkillDefinition | None:
    """Get a skill definition by ID."""
    return SKILL_DEFINITIONS.get(skill_id)


def list_skills() -> list[dict[str, Any]]:
    """List all available skills."""
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "supports_streaming": skill.supports_streaming,
            "supports_session": skill.supports_session,
            "category": skill.category,
        }
        for skill in SKILL_DEFINITIONS.values()
    ]


def get_skills_config() -> dict[str, Any]:
    """
    Return the skills configuration for OpenClaw integration.

    This produces the config that OpenClaw expects for registering
    skills as agent capabilities.
    """
    return {
        "skills": {
            "opencode": {
                "name": "OpenCode",
                "description": "AI coding assistant via OpenCode CLI",
                "type": "cli",
                "command": ["opencode", "run", "--format", "json"],
                "parser": "parsed.part.text",
                "auth": {
                    "type": "none",
                    "note": "Free models (-free suffix) need no auth. "
                    "Optional: set OPENCODE_API_KEY for paid models.",
                },
                "models": [
                    "mimo-v2-pro-free",
                ],
            },
            "codex": {
                "name": "Codex",
                "description": "AI coding assistant via Codex CLI (ChatGPT OAuth)",
                "type": "cli",
                "command": ["codex", "run", "--format", "json"],
                "parser": "parsed.item.text",
                "auth": {
                    "type": "oauth",
                    "provider": "chatgpt",
                    "setup": (
                        "Run 'openclaw configure' to authenticate via ChatGPT OAuth"
                    ),
                    "env_vars": ["CHATGPT_OAUTH_TOKEN"],
                },
                "models": ["codex-mini-latest", "o4-mini", "gpt-4.1"],
            },
            "coding-supervisor": {
                "name": "Coding Supervisor",
                "description": (
                    "Monitors AI coding sessions. Reviews diffs, runs tests, "
                    "validates changes, and provides structured feedback."
                ),
                "type": "internal",
                "supervises": ["opencode", "codex"],
            },
        }
    }


class CodingSupervisor:
    """
    In-process skill that supervises AI coding sessions.

    Watches file changes, validates code quality, runs tests,
    and provides feedback to the coding agent.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def start_session(self, session_id: str | None = None) -> str:
        """Start a new supervision session."""
        sid = session_id or uuid.uuid4().hex[:16]
        self._sessions[sid] = {
            "started_at": time.time(),
            "status": SkillStatus.RUNNING,
            "changes": [],
            "feedback": [],
        }
        logger.info("Coding supervisor session started: %s", sid)
        return sid

    def log_change(
        self,
        session_id: str,
        file_path: str,
        change_type: str,
        diff: str = "",
    ) -> None:
        """Log a code change in the supervised session."""
        session = self._sessions.get(session_id)
        if not session:
            return
        session["changes"].append(
            {
                "timestamp": time.time(),
                "file": file_path,
                "type": change_type,
                "diff": diff[:1000],
            }
        )

    def add_feedback(
        self,
        session_id: str,
        feedback: str,
        severity: str = "info",
    ) -> None:
        """Add feedback to a supervised session."""
        session = self._sessions.get(session_id)
        if not session:
            return
        session["feedback"].append(
            {
                "timestamp": time.time(),
                "message": feedback,
                "severity": severity,
            }
        )

    def end_session(
        self,
        session_id: str,
        status: SkillStatus = SkillStatus.COMPLETED,
    ) -> dict[str, Any]:
        """End a supervision session and return summary."""
        session = self._sessions.get(session_id, {})
        session["status"] = status
        session["ended_at"] = time.time()
        duration = session.get("ended_at", 0) - session.get("started_at", 0)

        summary = {
            "session_id": session_id,
            "status": status.value,
            "duration_s": round(duration, 1),
            "changes_count": len(session.get("changes", [])),
            "feedback_count": len(session.get("feedback", [])),
            "feedback": session.get("feedback", []),
        }

        logger.info(
            "Coding supervisor session %s ended: %s (%d changes, %d feedback)",
            session_id,
            status.value,
            summary["changes_count"],
            summary["feedback_count"],
        )
        return summary

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session state."""
        return self._sessions.get(session_id)


# Singleton supervisor
_supervisor: CodingSupervisor | None = None


def get_supervisor() -> CodingSupervisor:
    """Get the singleton coding supervisor."""
    global _supervisor
    if _supervisor is None:
        _supervisor = CodingSupervisor()
    return _supervisor
