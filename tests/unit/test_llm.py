from unittest.mock import patch, MagicMock
import httpx
import respx
import pytest
from rag.llm import ClaudeCLIBackend, OllamaBackend, route_query


def test_claude_cli_shells_out():
    with patch("rag.llm.subprocess.run") as run:
        run.return_value = MagicMock(stdout="Claude's answer.\n", returncode=0, stderr="")
        be = ClaudeCLIBackend()
        out = be.generate(system="sys", user="hello?")
        assert out == "Claude's answer."
        # Verify the claude CLI was invoked.
        run.assert_called_once()
        cmd = run.call_args[0][0]
        assert cmd[0] == "claude"


def test_claude_cli_propagates_failure():
    with patch("rag.llm.subprocess.run") as run:
        run.return_value = MagicMock(stdout="", returncode=2, stderr="auth required")
        with pytest.raises(RuntimeError, match="auth required"):
            ClaudeCLIBackend().generate(system="s", user="u")


@respx.mock
def test_ollama_backend_calls_chat_endpoint():
    respx.post("http://localhost:11434/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "Ollama's answer."}})
    )
    be = OllamaBackend(model="qwen2.5:7b", base_url="http://localhost:11434")
    assert be.generate(system="s", user="u") == "Ollama's answer."


def test_route_query_uses_private_prefix():
    claude = MagicMock(); claude.generate.return_value = "C"
    ollama = MagicMock(); ollama.generate.return_value = "O"
    text, is_private = route_query("private: my question", claude=claude, ollama=ollama,
                                   private_prefix="private:", default="claude-cli",
                                   private_routes_to="ollama")
    assert text == "my question"
    assert is_private is True


def test_route_query_default():
    claude = MagicMock(); claude.generate.return_value = "C"
    ollama = MagicMock(); ollama.generate.return_value = "O"
    text, is_private = route_query("normal question", claude=claude, ollama=ollama,
                                   private_prefix="private:", default="claude-cli",
                                   private_routes_to="ollama")
    assert text == "normal question"
    assert is_private is False
