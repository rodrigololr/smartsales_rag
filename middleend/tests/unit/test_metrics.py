"""M04 pure rules: the metrics window and the hourly 5xx counter buckets."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.config import Settings
from app.metrics import DEFAULT_METRICS_WINDOW, InvalidMetricsWindow, resolve_window
from app.telemetry.http_errors import COUNTER_RETENTION, error_5xx_rate, hour_keys
from redis.exceptions import ConnectionError as RedisConnectionError

NOW = datetime(2026, 11, 20, 14, 30, tzinfo=UTC)


def test_window_defaults_to_the_last_seven_days() -> None:
    window = resolve_window(None, None, NOW)
    assert (window.window_from, window.window_to) == (NOW - DEFAULT_METRICS_WINDOW, NOW)
    assert DEFAULT_METRICS_WINDOW == timedelta(days=7)


def test_window_from_only_runs_until_now_and_to_only_looks_back_seven_days() -> None:
    start = datetime(2026, 11, 1, tzinfo=UTC)
    assert resolve_window(start, None, NOW).window_to == NOW
    assert resolve_window(None, start, NOW).window_from == start - DEFAULT_METRICS_WINDOW


@pytest.mark.parametrize("offset", [timedelta(0), timedelta(hours=1)])
def test_window_must_end_after_it_starts(offset: timedelta) -> None:
    with pytest.raises(InvalidMetricsWindow):
        resolve_window(NOW, NOW - offset, NOW)


def test_window_serializes_with_the_contract_field_names() -> None:
    window = resolve_window(None, None, NOW).model_dump(mode="json", by_alias=True)
    assert set(window) == {"from", "to"}


def test_hour_keys_cover_every_hour_touched_by_the_window() -> None:
    start = datetime(2026, 11, 20, 11, 15, tzinfo=UTC)
    assert hour_keys(start, NOW, NOW) == [
        "metrics:http:2026112011",
        "metrics:http:2026112012",
        "metrics:http:2026112013",
        "metrics:http:2026112014",
    ]


def test_hour_keys_end_is_exclusive_and_offsets_are_normalized_to_utc() -> None:
    brasilia = datetime(2026, 11, 20, 6, 0, tzinfo=timezone(timedelta(hours=-3)))
    assert hour_keys(brasilia, brasilia + timedelta(hours=1), NOW) == ["metrics:http:2026112009"]


def test_hour_keys_are_clamped_to_retention_and_to_now() -> None:
    keys = hour_keys(datetime(2000, 1, 1, tzinfo=UTC), NOW + timedelta(days=365), NOW)
    assert len(keys) == COUNTER_RETENTION // timedelta(hours=1) + 1
    assert keys[-1] == "metrics:http:2026112014"
    assert hour_keys(datetime(2000, 1, 1, tzinfo=UTC), datetime(2000, 1, 2, tzinfo=UTC), NOW) == []


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_blank_admin_token_means_the_endpoint_is_closed(configured: str | None) -> None:
    assert Settings(admin_token=configured).admin_token is None


def test_admin_token_is_kept_secret_in_settings_repr() -> None:
    settings = Settings(admin_token="segredo")
    assert "segredo" not in repr(settings)
    assert settings.admin_token is not None
    assert settings.admin_token.get_secret_value() == "segredo"


class _BrokenPipeline:
    async def __aenter__(self) -> "_BrokenPipeline":
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def hmget(self, *args: object) -> None:
        return None

    async def execute(self) -> list[list[str | None]]:
        raise RedisConnectionError("redis down")


class _BrokenRedis:
    def pipeline(self, transaction: bool = False) -> _BrokenPipeline:
        return _BrokenPipeline()


def test_error_rate_degrades_to_zero_when_redis_is_down() -> None:
    # The summary page must still load: the 5xx rate is the only Redis-backed metric.
    now = datetime(2026, 11, 20, 12, tzinfo=UTC)
    rate = asyncio.run(
        error_5xx_rate(_BrokenRedis(), now - timedelta(hours=2), now, now)  # type: ignore[arg-type]
    )
    assert rate == 0.0
