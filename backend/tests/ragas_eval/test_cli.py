"""Offline validation must never certify quality or silently call a live provider."""

import sys

import pytest

from . import eval_runner


@pytest.mark.parametrize("gate, expected", [(False, 0), (True, 1)])
def test_validate_mode_is_pending_and_has_no_model_calls(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    gate: bool,
    expected: int,
) -> None:
    args = ["eval_runner", "--mode", "validate"] + (["--gate-check"] if gate else [])
    monkeypatch.setattr(sys, "argv", args)

    async def forbidden_live(*args: object, **kwargs: object) -> None:
        raise AssertionError("Offline validation called a provider")

    monkeypatch.setattr(eval_runner, "_live", forbidden_live)
    assert eval_runner.main() == expected
    output = capsys.readouterr().out
    assert "PENDING" in output and "Casos: 0/50" in output


def test_live_mode_without_credentials_fails_before_any_model_factory(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in ("LLM_API_KEY", "OPENAI_API_KEY", "EVAL_JUDGE_API_KEY", "EVAL_JUDGE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", ["eval_runner", "--mode", "live", "--gate-check"])
    calls: list[str] = []

    def forbidden_client(*args: object, **kwargs: object) -> None:
        calls.append("client")
        raise AssertionError("Unexpected client factory")

    monkeypatch.setattr(eval_runner, "make_client", forbidden_client)
    assert eval_runner.main() == 2
    assert not calls and "unavailable" in capsys.readouterr().out
