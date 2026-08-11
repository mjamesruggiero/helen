"""Tests for helen.clean — pure parsing/cleaning functions.

TDD: these tests are the SPEC. Your job is to implement the functions in
helen/clean.py until every test here passes (red -> green).

Start with `parse_amount`. Run just its tests with:

    pytest tests/test_clean.py -k parse_amount -v
"""
import pytest

from helen.clean import parse_amount


class TestParseAmount:
    """`parse_amount(raw) -> float`

    The AMOUNT column in the CSV arrives as a string like "-7.99" or "6541.46".
    Some bank exports include thousands separators, e.g. "-1,234.56", and stray
    quotes/whitespace. Your function should return a float in all these cases.
    If the same value is already a number, it should pass through unchanged.
    Empty / non-numeric input should raise (let float() do the raising).
    """

    def test_simple_negative(self):
        assert parse_amount("-7.99") == -7.99

    def test_simple_positive(self):
        assert parse_amount("6541.46") == 6541.46

    def test_strips_thousands_separator(self):
        assert parse_amount("-1,234.56") == -1234.56

    def test_strips_stray_quotes_and_whitespace(self):
        assert parse_amount('  "-100.00" ') == -100.00

    def test_passes_through_float(self):
        assert parse_amount(6541.46) == 6541.46

    def test_passes_through_int(self):
        assert parse_amount(-100) == -100.0

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            parse_amount("")
