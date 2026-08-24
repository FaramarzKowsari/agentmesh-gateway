from __future__ import annotations

from agentmesh.portable import normalized_argv


def test_portable_defaults_to_serve_when_no_command_is_given() -> None:
    assert normalized_argv(["AgentMesh-Gateway"]) == ["AgentMesh-Gateway", "serve"]


def test_portable_preserves_explicit_command() -> None:
    assert normalized_argv(["AgentMesh-Gateway", "version"]) == [
        "AgentMesh-Gateway",
        "version",
    ]
