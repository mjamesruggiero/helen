"""Tests for helen.categorize — pure categorization functions.

TDD: these tests are the SPEC. Implement helen/categorize.py until they pass.
Start with the scalar `categorize_merchant`:

    pytest tests/test_categorize.py -k categorize_merchant -v

Then build the DataFrame-level `categorize` (tests at the bottom).
"""
import pandas as pd
import pytest

from helen.categorize import categorize_merchant, categorize


# A small ruleset reused across tests. Order matters: first match wins.
RULES = {
    "Groceries":     ["WHOLEFDS", "VONS", "TRADER JOE"],
    "Dining":        ["IRVSBURGERS", "DESANO", "WESTWOOD CAFE"],
    "Fuel":          ["CHEVRON", "FHDA FUEL"],
    "Subscriptions": ["APPLE.COM/BILL", "ADOBE", "AMAZON WEB SERVICE"],
    "Transfers":     ["VENMO", "PAYPAL", "SCHWAB"],
    "Income":        ["PAYROLL"],
}


class TestCategorizeMerchant:
    """`categorize_merchant(merchant, category_rules) -> str`

    Case-insensitive SUBSTRING match. Iterate categories in insertion order and
    return the first category that has any matching substring. No match ->
    "Uncategorized".
    """

    def test_exact_ish_grocery(self):
        assert categorize_merchant("VONS", RULES) == "Groceries"

    def test_substring_match_with_location_noise(self):
        # merchant strings from clean() carry location/store-number cruft
        m = "WHOLEFDS PLV #10 12746 W PLAYA VISTA"
        assert categorize_merchant(m, RULES) == "Groceries"

    def test_case_insensitive(self):
        assert categorize_merchant("chevron 0386062", RULES) == "Fuel"

    def test_dining(self):
        assert categorize_merchant("IRVSBURGERS", RULES) == "Dining"

    def test_subscription(self):
        assert categorize_merchant("APPLE.COM/BILL 866-712-7753", RULES) == "Subscriptions"

    def test_transfer(self):
        assert categorize_merchant("VENMO *MICHAEL COLLIER", RULES) == "Transfers"

    def test_income(self):
        assert categorize_merchant("ASF, DBA INSPERI PAYROLL", RULES) == "Income"

    def test_no_match_is_uncategorized(self):
        assert categorize_merchant("SOME RANDOM SHOP 123", RULES) == "Uncategorized"

    def test_first_match_wins(self):
        # If a merchant could hit two categories, the earlier-listed one wins.
        rules = {
            "A": ["FOO"],
            "B": ["BAR"],
        }
        assert categorize_merchant("FOO BAR BAZ", rules) == "A"

    def test_empty_rules_gives_uncategorized(self):
        assert categorize_merchant("WHOLEFDS", {}) == "Uncategorized"


class TestCategorizeDataFrame:
    """`categorize(df, category_rules) -> df`

    Adds a 'category' column via categorize_merchant. Must NOT mutate the input.
    """

    def _frame(self):
        return pd.DataFrame(
            {
                "merchant": ["VONS", "IRVSBURGERS", "VENMO *X", "MYSTERY LLC"],
                "amount": [-67.22, -38.68, -440.0, -12.0],
            }
        )

    def test_adds_category_column(self):
        out = categorize(self._frame(), RULES)
        assert list(out["category"]) == ["Groceries", "Dining", "Transfers", "Uncategorized"]

    def test_does_not_mutate_input(self):
        df = self._frame()
        _ = categorize(df, RULES)
        assert "category" not in df.columns
