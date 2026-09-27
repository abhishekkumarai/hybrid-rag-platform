"""Shared unit-test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_sampled_llm_judge(monkeypatch):
    """Disable the sampled background LLM judge (IRA-14) for every unit test.

    It fires on a random ~10% of answered turns and calls `requests.post` from a thread, so tests
    that patch `requests.post` and inspect `call_args` would otherwise flakily see the judge's call
    instead of the generation call. Tests that exercise the judge pass `sample_rate` explicitly."""
    from services.gateway import api

    monkeypatch.setattr(api.settings.evaluation, "llm_judge_sample_rate", 0.0)
