"""Trading memory — session context storage and keyword-based recall.

v0.1 uses JSON files and simple keyword matching.
Vector search is planned for v0.2.

Source: distillation-plan-supplement-3, gap 18.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pnlclaw_types.agent import ChatMessage

_DEFAULT_MEMORY_DIR = Path.home() / ".pnlclaw" / "memory"


class TradingMemory:
    """Session-based trading knowledge store.

    Saves conversation summaries as JSON files and recalls relevant
    context via keyword matching for prompt injection.

    Storage: ``~/.pnlclaw/memory/sessions/{session_id}.json``
    """

    def __init__(self, memory_dir: Path | None = None) -> None:
        self._root = memory_dir or _DEFAULT_MEMORY_DIR
        self._sessions_dir = self._root / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def save_context(
        self,
        session_id: str,
        messages: list[ChatMessage],
        summary: str = "",
    ) -> None:
        """Save a session summary to disk.

        Args:
            session_id: Unique session identifier.
            messages: Conversation messages from the session.
            summary: Optional pre-generated summary. If empty, a basic
                summary is extracted from the messages.
        """
        if not summary:
            summary = self._auto_summary(messages)

        # Extract key facts
        tools_used = set()
        symbols_mentioned = set()
        for msg in messages:
            if msg.metadata:
                tool = msg.metadata.get("tool_name")
                if tool:
                    tools_used.add(tool)
            # Simple symbol detection
            for word in msg.content.split():
                if "/" in word and len(word) <= 12:
                    cleaned = word.strip(".,;:!?\"'()")
                    if cleaned.isupper() or any(c.isupper() for c in cleaned):
                        symbols_mentioned.add(cleaned)

        data = {
            "session_id": session_id,
            "summary": summary,
            "tools_used": sorted(tools_used),
            "symbols": sorted(symbols_mentioned),
            "message_count": len(messages),
            "timestamp": int(time.time() * 1000),
        }

        path = self._sessions_dir / f"{session_id}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def recall_for_prompt(self, context: dict[str, Any]) -> str:
        """Recall relevant prior session context for prompt injection.

        Uses keyword matching (symbols, tool names) against recent
        session summaries. Returns up to ~500 tokens of relevant text.

        Args:
            context: Dict with optional keys:
                - ``symbols``: list of symbols being discussed
                - ``tools``: list of tools being used
                - ``keywords``: list of additional keywords

        Returns:
            Formatted string of relevant prior context, or empty string.
        """
        sessions = self._load_recent_sessions(limit=20)
        if not sessions:
            return ""

        # Build keyword set from context
        keywords: set[str] = set()
        for sym in context.get("symbols", []):
            keywords.add(sym.upper())
        for tool in context.get("tools", []):
            keywords.add(tool.lower())
        for kw in context.get("keywords", []):
            keywords.add(kw.lower())

        if not keywords:
            return ""

        # Score each session by keyword overlap
        scored: list[tuple[float, dict[str, Any]]] = []
        for session in sessions:
            score = 0.0
            session_text = (
                session.get("summary", "").lower()
                + " "
                + " ".join(session.get("symbols", []))
                + " "
                + " ".join(session.get("tools_used", []))
            )
            for kw in keywords:
                if kw.lower() in session_text:
                    score += 1.0
            if score > 0:
                scored.append((score, session))

        if not scored:
            return ""

        # Sort by score descending, take top 3
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:3]

        parts: list[str] = []
        char_budget = 2000  # ~500 tokens
        used = 0

        for _, session in top:
            entry = f"- {session.get('summary', '(no summary)')}"
            if used + len(entry) > char_budget:
                break
            parts.append(entry)
            used += len(entry)

        return "\n".join(parts) if parts else ""

    def list_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """List recent sessions ordered by modification time.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            List of session data dicts.
        """
        return self._load_recent_sessions(limit=limit)

    def clear(self) -> None:
        """Remove all session files."""
        if self._sessions_dir.exists():
            for f in self._sessions_dir.glob("*.json"):
                f.unlink()

    # -- internal ------------------------------------------------------------

    def _load_recent_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        """Load recent session files sorted by modification time."""
        if not self._sessions_dir.exists():
            return []

        files = sorted(
            self._sessions_dir.glob("*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        sessions: list[dict[str, Any]] = []
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                sessions.append(data)
            except (json.JSONDecodeError, OSError):
                continue
        return sessions

    def _auto_summary(self, messages: list[ChatMessage]) -> str:
        """Extract a basic summary from conversation messages."""
        # Find the last user message as the topic
        user_msgs = [m for m in messages if m.role == "user"]
        if user_msgs:
            last_user = user_msgs[-1].content[:200]
            return f"User asked: {last_user}"
        return f"Session with {len(messages)} messages"
