import json
from pathlib import Path

import pytest
from app.config import Settings
from pydantic import SecretStr

from .checkpoint import (
    CheckpointMismatch,
    load_checkpoint,
    make_identity,
    safe_endpoint,
    save_checkpoint,
)
from .corpus import Corpus
from .eval_runner import DEFAULT_FIXTURE_PATH, ROOT
from .judge import JudgeSettings
from .models import EvalCaseResult, RunIdentity


def test_legacy_mock_checkpoint_cannot_be_reused(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    path.write_text(json.dumps([{"case_id": "RAGAS-GS-01", "details": {"mode": "mock"}}]))
    with pytest.raises(CheckpointMismatch):
        load_checkpoint(path, RunIdentity(mode="live", fingerprint="live-config"))


def test_cross_configuration_checkpoint_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "checkpoint.json"
    result = EvalCaseResult(case_id="case", expected_action="ANSWER", actual_action="ANSWER")
    save_checkpoint(path, RunIdentity(mode="test", fingerprint="offline-config"), [result])
    with pytest.raises(CheckpointMismatch):
        load_checkpoint(path, RunIdentity(mode="live", fingerprint="live-config"))
    assert (
        load_checkpoint(path, RunIdentity(mode="test", fingerprint="offline-config"))[
            "case"
        ].case_id
        == "case"
    )


def test_identity_includes_behavioral_settings_and_omits_credentials(corpus: Corpus) -> None:
    settings = Settings(llm_api_key="SECRET_GENERATOR")
    judge = JudgeSettings(judge_api_key=SecretStr("SECRET_JUDGE"), judge_model="independent-model")
    first = make_identity(ROOT, DEFAULT_FIXTURE_PATH, corpus, settings, judge, mode="live")
    second = make_identity(
        ROOT,
        DEFAULT_FIXTURE_PATH,
        corpus,
        settings.model_copy(update={"similarity_threshold": 0.42}),
        judge,
        mode="live",
    )
    assert first.fingerprint != second.fingerprint
    assert "SECRET_" not in first.model_dump_json()
    assert (
        safe_endpoint("https://user:password@example.com:8443/v1?token=secret")
        == "https://example.com:8443/v1"
    )


def test_fixture_or_mode_change_invalidates_identity(corpus: Corpus, tmp_path: Path) -> None:
    settings = Settings()
    original = make_identity(ROOT, DEFAULT_FIXTURE_PATH, corpus, settings, None, mode="validate")
    changed_path = tmp_path / "fixtures.json"
    changed_path.write_bytes(DEFAULT_FIXTURE_PATH.read_bytes() + b" ")
    changed = make_identity(ROOT, changed_path, corpus, settings, None, mode="validate")
    other_mode = make_identity(ROOT, DEFAULT_FIXTURE_PATH, corpus, settings, None, mode="test")
    assert len({original.fingerprint, changed.fingerprint, other_mode.fingerprint}) == 3


def test_identity_never_serializes_redis_credentials(corpus: Corpus) -> None:
    settings = Settings(redis_url="redis://user:PRIVATE_REDIS_PASSWORD@localhost:6379/0")
    identity = make_identity(ROOT, DEFAULT_FIXTURE_PATH, corpus, settings, None, mode="validate")
    assert "PRIVATE_REDIS_PASSWORD" not in identity.model_dump_json()


def test_identity_tracks_the_embedding_endpoint_without_its_credentials(corpus: Corpus) -> None:
    settings = Settings(llm_api_key="SECRET_GENERATOR")
    shared = JudgeSettings(judge_api_key=SecretStr("SECRET_JUDGE"), judge_model="independent-model")
    separate = shared.model_copy(
        update={
            "embedding_api_key": SecretStr("SECRET_EMBEDDING"),
            "embedding_base_url": "https://user:pw@embeddings.example/v1?token=SECRET_URL",
        }
    )
    first = make_identity(ROOT, DEFAULT_FIXTURE_PATH, corpus, settings, shared, mode="live")
    second = make_identity(ROOT, DEFAULT_FIXTURE_PATH, corpus, settings, separate, mode="live")
    assert first.fingerprint != second.fingerprint
    dumped = second.model_dump_json()
    assert "SECRET_" not in dumped
    assert "https://embeddings.example/v1" in dumped
