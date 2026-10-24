"""Answer-quality guards found by running real test queries."""
from api.agents import compliance_agent


def test_prompt_no_longer_asks_for_an_unverifiable_procedural_note():
    assert "PROCEDURAL NOTE" not in compliance_agent.SYSTEM_PROMPT
    assert "no commentary of your own" in compliance_agent.SYSTEM_PROMPT
