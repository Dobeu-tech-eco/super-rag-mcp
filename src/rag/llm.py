"""LLM generation backends. Claude Code CLI (Max auth) + Ollama local."""
from __future__ import annotations
import subprocess
from typing import Literal, Protocol
import httpx


class LLMBackend(Protocol):
    def generate(self, system: str, user: str) -> str: ...


class ClaudeCLIBackend:
    """Shells out to the Claude Code CLI. Uses the user's Max subscription auth."""

    def __init__(self, command: str = "claude", timeout: float = 120.0) -> None:
        self.command = command
        self.timeout = timeout

    def generate(self, system: str, user: str) -> str:
        prompt = f"<system>\n{system}\n</system>\n<user>\n{user}\n</user>"
        result = subprocess.run(
            [self.command, "--print", prompt],
            capture_output=True, text=True, timeout=self.timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "claude CLI failed")
        return result.stdout.strip()


class OllamaBackend:
    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 timeout: float = 120.0) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def generate(self, system: str, user: str) -> str:
        resp = self._client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


def route_query(
    raw: str,
    claude: LLMBackend,
    ollama: LLMBackend,
    private_prefix: str = "private:",
    default: Literal["claude-cli", "ollama"] = "claude-cli",
    private_routes_to: Literal["claude-cli", "ollama"] = "ollama",
) -> tuple[str, bool]:
    """Strip the private prefix if present and return (cleaned_text, is_private)."""
    if raw.lstrip().lower().startswith(private_prefix.lower()):
        return raw.lstrip()[len(private_prefix):].lstrip(), True
    return raw, False
