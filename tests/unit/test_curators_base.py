"""Curator Protocol conformance tests."""
from __future__ import annotations

from claude_almanac.curators import Curator


class _StubCurator:
    name = "stub"
    model = "stub-model"
    timeout_s = 1.0

    def invoke(self, system_prompt: str, user_turn: str) -> str:
        return "{}"


def test_stub_curator_conforms_to_protocol() -> None:
    c: Curator = _StubCurator()
    assert c.name == "stub"
    assert c.model == "stub-model"
    assert c.invoke("sys", "user") == "{}"


def test_protocol_runtime_checkable() -> None:
    assert isinstance(_StubCurator(), Curator)
