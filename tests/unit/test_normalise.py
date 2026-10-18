from datetime import date

import pytest

from copilot.adapters.normalise import blank, parse_bool, parse_date, parse_money


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("S$1,234.50", "1234.50"),
        ("$99", "99"),
        ("-4,500.00", "-4500.00"),
        (" 12.30 ", "12.30"),
        ("", None),
        (None, None),
    ],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["12.3.4", "abc", "1,2a", "--5"])
def test_parse_money_rejects_garbage(raw):
    with pytest.raises(ValueError):
        parse_money(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-01", date(2026, 9, 1)),
        ("01/09/2026", date(2026, 9, 1)),  # Singapore day-first
        ("1/9/2026", date(2026, 9, 1)),
        ("", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["09/31/2026", "2026/09/30", "2026-02-30", "Sept 1 2026"])
def test_parse_date_rejects_bad_or_ambiguous(raw):
    with pytest.raises(ValueError):
        parse_date(raw)


def test_parse_bool():
    assert parse_bool("Yes") is True
    assert parse_bool("0") is False
    assert parse_bool(" ") is None
    with pytest.raises(ValueError):
        parse_bool("maybe")


def test_blank():
    assert blank("  x ") == "x"
    assert blank("   ") is None
