"""Live scripted conversational suite against the public SSE gateway (spec §9).

Skipped unless LIVE_API_BASE_URL is set. Paces LLM turns (KB_QA / TECHNICAL) to <= 10 RPM.
"""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

LIVE_API_BASE_URL = os.environ.get("LIVE_API_BASE_URL", "").rstrip("/")
DIALOGS_PATH = Path(__file__).resolve().parents[1] / "conversational" / "dialogs.json"
LLM_MIN_INTERVAL_SECONDS = 6.5  # <= 10 RPM for Gemini free tier

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not LIVE_API_BASE_URL, reason="LIVE_API_BASE_URL not set"),
]

_last_llm_call_at = 0.0


def _parse_sse(raw_text: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    event_name = ""
    data_lines: list[str] = []
    for line in raw_text.splitlines():
        if line.startswith("event:"):
            event_name = line.partition(":")[2].strip()
        elif line.startswith("data:"):
            data_lines.append(line.partition(":")[2].strip())
        elif not line.strip() and event_name and data_lines:
            payload = json.loads("\n".join(data_lines))
            events.append((event_name, payload))
            event_name = ""
            data_lines = []
    if event_name and data_lines:
        events.append((event_name, json.loads("\n".join(data_lines))))
    return events


@pytest.mark.parametrize(
    "dialog",
    json.loads(DIALOGS_PATH.read_text(encoding="utf-8")),
    ids=lambda d: d["id"],
)
def test_live_consultor_dialogs(dialog: dict[str, object]) -> None:
    global _last_llm_call_at
    with httpx.Client(base_url=LIVE_API_BASE_URL, timeout=30.0) as client:
        session_resp = client.post("/api/v1/sessions", json={})
        assert session_resp.status_code in (200, 201)
        session_id = session_resp.json()["session_id"]

        turns: list[dict[str, object]] = dialog["turns"]  # type: ignore[assignment]
        for turn in turns:
            if turn.get("llm_turn"):
                elapsed = time.monotonic() - _last_llm_call_at
                if elapsed < LLM_MIN_INTERVAL_SECONDS:
                    time.sleep(LLM_MIN_INTERVAL_SECONDS - elapsed)
                _last_llm_call_at = time.monotonic()

            body: dict[str, object] = {
                "session_id": session_id,
                "message": turn["question"],
                "client_request_id": str(uuid4()),
            }
            if turn.get("sku") is not None:
                body["context_filters"] = {"current_product_sku": turn["sku"]}

            response = client.post("/api/v1/chat/stream", json=body)
            assert response.status_code == 200
            sse_events = _parse_sse(response.text)
            names = [name for name, _ in sse_events]
            assert names[0] == "metadata" and names[-1] == "done"

            if turn.get("expect_error"):
                err_events = [data for name, data in sse_events if name == "error"]
                assert err_events and err_events[0]["code"] == turn["expect_error"]
                published = str(err_events[0].get("fallback_message", ""))
            else:
                published = "".join(
                    str(data.get("delta", ""))
                    for name, data in sse_events
                    if name == "token"
                )

            for phrase in turn.get("must_contain", ()):  # type: ignore[attr-defined]
                assert str(phrase) in published
            for forbidden in turn.get("must_not_contain", ()):  # type: ignore[attr-defined]
                assert str(forbidden) not in published

            rec_events = [data for name, data in sse_events if name == "recommendations"]
            cards = rec_events[0]["products"] if rec_events else []  # type: ignore[index]
            expected_skus = list(turn.get("expected_card_skus", ()))  # type: ignore[arg-type]
            if expected_skus:
                assert [c["sku"] for c in cards] == expected_skus
