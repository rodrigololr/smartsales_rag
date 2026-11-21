"""Immutable run identity and atomic, configuration-bound checkpoints."""

import importlib.metadata
import json
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from app.config import Settings
from pydantic import Field, model_validator

from .corpus import Corpus, digest, stable_json
from .judge import JudgeSettings
from .models import EvalCaseResult, RunIdentity, StrictModel

B04_BASELINE_REVISION = "0181b2030df63e73c0a4abb6be7a54b22383950c"


class CheckpointMismatch(ValueError):
    """No legacy, stale or cross-mode checkpoint is valid for the current run."""


class Checkpoint(StrictModel):
    schema_version: int = 2
    fingerprint: str
    results: dict[str, EvalCaseResult] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_case_keys(self) -> "Checkpoint":
        if any(key != result.case_id for key, result in self.results.items()):
            raise ValueError("Checkpoint result IDs differ from their keys")
        return self


def safe_endpoint(url: str | None) -> str:
    parsed = urlsplit(url or "https://api.openai.com/v1")
    host = parsed.hostname or ""
    host = f"[{host}]" if ":" in host else host
    authority = f"{host}:{parsed.port}" if parsed.port is not None else host
    return urlunsplit((parsed.scheme, authority, parsed.path, "", ""))


def code_revision(root: Path) -> tuple[str, bool]:
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        return revision, not bool(dirty)
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN", False


def has_integrated_b04(root: Path) -> bool:
    try:
        return (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", B04_BASELINE_REVISION, "HEAD"],
                cwd=root,
                capture_output=True,
                check=False,
            ).returncode
            == 0
        )
    except OSError:
        return False


def audit_approved(root: Path, fixture_digest: str, corpus_digest: str) -> bool:
    path = root / "backend/tests/ragas_eval/audit.json"
    if not path.is_file():
        return False
    approval = json.loads(path.read_bytes())
    return (
        approval.get("status") == "approved"
        and bool(approval.get("reviewed_by"))
        and bool(approval.get("reviewed_at"))
        and approval.get("fixture_sha256") == fixture_digest
        and approval.get("corpus_sha256") == corpus_digest
    )


def make_identity(
    root: Path,
    fixture_path: Path,
    corpus: Corpus,
    settings: Settings,
    judge: JudgeSettings | None,
    *,
    mode: str,
) -> RunIdentity:
    revision, clean = code_revision(root)
    code = {
        str(path.relative_to(root)): digest(path.read_bytes())
        for folder in (root / "backend/app", root / "backend/tests/ragas_eval")
        for path in sorted(folder.rglob("*.py"))
    }
    for name in (
        "backend/requirements.txt",
        "backend/requirements-eval.txt",
        "backend/requirements-eval.lock",
        "backend/tests/ragas_eval/audit.json",
    ):
        code[name] = digest((root / name).read_bytes())
    configuration: dict[str, str | int | float | bool | None] = {
        key: value
        for key, value in settings.model_dump().items()
        if key not in {"llm_api_key", "database_url", "llm_base_url", "redis_url"}
    }
    configuration["generator_endpoint"] = safe_endpoint(settings.llm_base_url)
    configuration["generator_endpoint_sha256"] = digest((settings.llm_base_url or "").encode())
    configuration["index_embeddings_sha256"] = corpus.embeddings_sha256
    configuration["index_uuids_sha256"] = digest(stable_json(corpus.database_ids))
    if judge is not None:
        configuration.update(
            {
                f"judge_{key}": value
                for key, value in judge.model_dump().items()
                if key
                not in {"judge_api_key", "judge_base_url", "embedding_api_key", "embedding_base_url"}
            }
        )
        configuration["judge_endpoint"] = safe_endpoint(judge.judge_base_url)
        configuration["judge_endpoint_sha256"] = digest((judge.judge_base_url or "").encode())
        embedding_url = judge.embedding_endpoint()[1]
        configuration["judge_embedding_endpoint"] = safe_endpoint(embedding_url)
        configuration["judge_embedding_endpoint_sha256"] = digest((embedding_url or "").encode())
        configuration["judge_embedding_dedicated_key"] = judge.embedding_api_key is not None
    for package in ("ragas", "openai", "pydantic", "langchain-community", "langchain-openai"):
        try:
            configuration[f"version:{package}"] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            configuration[f"version:{package}"] = "not-installed"
    identity = RunIdentity.model_validate(
        {
            "mode": mode,
            "revision": revision,
            "clean_checkout": clean,
            "corpus_sha256": corpus.sha256,
            "fixture_sha256": digest(fixture_path.read_bytes()),
            "generator_model": settings.llm_model,
            "judge_model": judge.judge_model if judge else "",
            "configuration": configuration,
            "corpus_verified": corpus.verified,
            "integrated_b04": has_integrated_b04(root),
            "po_audit_approved": audit_approved(
                root, digest(fixture_path.read_bytes()), corpus.sha256
            ),
        }
    )
    identity.fingerprint = digest(
        stable_json({"identity": identity.model_dump(mode="json"), "code": code})
    )
    return identity


def load_checkpoint(path: Path | None, identity: RunIdentity) -> dict[str, EvalCaseResult]:
    if path is None or not path.is_file():
        return {}
    try:
        checkpoint = Checkpoint.model_validate_json(path.read_bytes())
    except ValueError as error:
        raise CheckpointMismatch("Legacy or invalid checkpoint; use a new file") from error
    if checkpoint.schema_version != 2 or checkpoint.fingerprint != identity.fingerprint:
        raise CheckpointMismatch(
            "Checkpoint mode/code/fixture/corpus/model/policy differs from this run"
        )
    return checkpoint.results


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(stable_json(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def save_checkpoint(
    path: Path | None, identity: RunIdentity, results: list[EvalCaseResult]
) -> None:
    if path is not None:
        checkpoint = Checkpoint(
            fingerprint=identity.fingerprint, results={r.case_id: r for r in results}
        )
        write_json(path, checkpoint.model_dump(mode="json"))
