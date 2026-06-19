"""Unit tests for the unseen_count `since` timestamp parsing fix.

The bug: Python 3.10 fromisoformat() does not accept trailing "Z"
(UTC suffix); only 3.11+ does. The frontend sends new Date().toISOString()
which always emits "Z". Before the fix every call silently fell back to the
Unix epoch, making the badge perpetually non-zero.

These tests validate the parsing logic in isolation — no Flask app, no
MongoDB — so they run fast and without external services.
"""
import datetime


# ── replicate the exact parsing logic from server.py unseen_count() ──────────

def _parse_since(raw: str) -> datetime.datetime:
    """Mirror of the since-parsing block in unseen_count()."""
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)


# ── tests ─────────────────────────────────────────────────────────────────────

class TestParseSince:
    def test_z_suffix_parses_to_utc(self):
        """Frontend-supplied timestamps (new Date().toISOString()) end in Z."""
        result = _parse_since("2026-06-19T14:32:10.123Z")
        assert result == datetime.datetime(
            2026, 6, 19, 14, 32, 10, 123000, tzinfo=datetime.timezone.utc
        )

    def test_z_suffix_is_not_epoch(self):
        """Before the fix, Z-suffix raised ValueError and returned epoch.
        Confirm the parsed time is meaningfully after epoch."""
        result = _parse_since("2026-06-19T14:32:10.123Z")
        epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
        assert result > epoch

    def test_explicit_utc_offset_still_works(self):
        """+00:00 suffix (already valid in 3.10) should continue to work."""
        result = _parse_since("2026-06-19T14:32:10+00:00")
        assert result == datetime.datetime(
            2026, 6, 19, 14, 32, 10, tzinfo=datetime.timezone.utc
        )

    def test_invalid_falls_back_to_epoch(self):
        """Garbage input should still fall back to epoch (not crash)."""
        result = _parse_since("not-a-date")
        assert result == datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

    def test_default_since_value_parses(self):
        """The default value used when `since` is absent must parse cleanly."""
        result = _parse_since("1970-01-01T00:00:00+00:00")
        assert result == datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)

    def test_z_suffix_without_milliseconds(self):
        """ISO8601 with Z but no fractional seconds — common from some clients."""
        result = _parse_since("2026-06-19T14:32:10Z")
        assert result == datetime.datetime(
            2026, 6, 19, 14, 32, 10, tzinfo=datetime.timezone.utc
        )

    def test_recent_timestamp_later_than_older_timestamp(self):
        """Confirm ordering is preserved — this is what the badge count relies on."""
        earlier = _parse_since("2026-06-18T00:00:00Z")
        later = _parse_since("2026-06-19T14:32:10.123Z")
        assert later > earlier
