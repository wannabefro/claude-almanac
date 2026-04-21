"""Tests for idle-fallback rollup trigger in UserPromptSubmit hook."""
from unittest.mock import patch

from claude_almanac.hooks.retrieve import _maybe_fire_idle_rollup


def test_fires_when_prior_session_stale_and_no_rollup(tmp_path):
    """When a stale prior transcript exists and no rollup, spawn runner."""
    prior = tmp_path / "prior.jsonl"
    prior.write_text("{}")
    with patch(
        "claude_almanac.hooks.retrieve._stale_prior_session",
        return_value=(prior, "prior-sid"),
    ), patch(
        "claude_almanac.hooks.retrieve._has_rollup", return_value=False,
    ), patch(
        "claude_almanac.hooks.retrieve._spawn_idle_rollup",
    ) as spawn:
        _maybe_fire_idle_rollup(
            current_session_id="current",
            idle_threshold_minutes=45,
            cwd=tmp_path,
        )
        assert spawn.call_count == 1


def test_does_not_fire_when_rollup_already_exists(tmp_path):
    """When a rollup already exists for the prior session, don't spawn."""
    prior = tmp_path / "prior.jsonl"
    prior.write_text("{}")
    with patch(
        "claude_almanac.hooks.retrieve._stale_prior_session",
        return_value=(prior, "prior-sid"),
    ), patch(
        "claude_almanac.hooks.retrieve._has_rollup", return_value=True,
    ), patch(
        "claude_almanac.hooks.retrieve._spawn_idle_rollup",
    ) as spawn:
        _maybe_fire_idle_rollup(
            current_session_id="current",
            idle_threshold_minutes=45,
            cwd=tmp_path,
        )
        assert spawn.call_count == 0


def test_does_not_fire_when_no_stale_prior(tmp_path):
    """When there is no stale prior session, don't spawn."""
    with patch(
        "claude_almanac.hooks.retrieve._stale_prior_session",
        return_value=None,
    ), patch(
        "claude_almanac.hooks.retrieve._spawn_idle_rollup",
    ) as spawn:
        _maybe_fire_idle_rollup(
            current_session_id="current",
            idle_threshold_minutes=45,
            cwd=tmp_path,
        )
        assert spawn.call_count == 0
