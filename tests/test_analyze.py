"""Tests for helen.analyze — pure analysis functions.

TDD: these tests are the SPEC. Implement helen/analyze.py until they pass, one
function at a time. Suggested order (matches the build guide):

    pytest "tests/test_analyze.py::TestMonthlyOutgo" -v
    pytest "tests/test_analyze.py::TestMonthlyByCategory" -v
    pytest "tests/test_analyze.py::TestIncomeVsOutgo" -v
    pytest "tests/test_analyze.py::TestAverageMonthlyOutgo" -v
    pytest "tests/test_analyze.py::TestDetectRecurring" -v

# Note: use the ::ClassName selector, NOT `-k monthly_outgo`. `-k` substring-matches
# the CamelCase class names, so `-k monthly_outgo` selects nothing.

Sign conventions (see the guide):
- `amount` is negative for spending, positive for money in.
- All "outgo"/"spend" functions return POSITIVE magnitudes.
- Transfers and Income are excluded from spend by default.
"""
import pandas as pd
import pytest

from helen.analyze import (
    monthly_outgo,
    monthly_by_category,
    income_vs_outgo,
    average_monthly_outgo,
    detect_recurring,
)


def _p(ym: str) -> pd.Period:
    return pd.Period(ym, freq="M")


def sample_df() -> pd.DataFrame:
    """Small hand-computable fixture spanning three months.

    Worked-out spend (excluding Transfers & Income):
      2025-01: Groceries 100 + Dining 50 + Subscriptions 12 = 162
      2025-02: Groceries 200 + Subscriptions 12             = 212
      2025-03: Dining 30 + Subscriptions 12                 =  42

    Income (positive, category == 'Income'):
      2025-01: 6000 ; 2025-02: 6000 ; 2025-03: 0

    Note: the +1000 SCHWAB row in 2025-02 is category 'Transfers' (money in), so it
    must NOT count as income and must NOT count as spend.

    Recurring: ADOBE (Subscriptions) appears in all 3 months at 12.00 -> recurring.
    VONS (2 months) and IRVSBURGERS (2 months) are below the 3-month threshold.
    """
    rows = [
        # 2025-01
        ("2025-01", "VONS",          -100.0, "Groceries"),
        ("2025-01", "IRVSBURGERS",    -50.0, "Dining"),
        ("2025-01", "ADOBE",          -12.0, "Subscriptions"),
        ("2025-01", "PAYROLL",       6000.0, "Income"),
        ("2025-01", "VENMO",         -400.0, "Transfers"),
        # 2025-02
        ("2025-02", "VONS",          -200.0, "Groceries"),
        ("2025-02", "ADOBE",          -12.0, "Subscriptions"),
        ("2025-02", "PAYROLL",       6000.0, "Income"),
        ("2025-02", "SCHWAB",        1000.0, "Transfers"),   # transfer IN, not income
        # 2025-03
        ("2025-03", "IRVSBURGERS",    -30.0, "Dining"),
        ("2025-03", "ADOBE",          -12.0, "Subscriptions"),
    ]
    df = pd.DataFrame(rows, columns=["month", "merchant", "amount", "category"])
    df["month"] = df["month"].map(_p)
    df["is_outflow"] = df["amount"] < 0
    return df


class TestMonthlyOutgo:
    def test_values_and_index(self):
        s = monthly_outgo(sample_df())
        assert list(s.index) == [_p("2025-01"), _p("2025-02"), _p("2025-03")]
        assert s.loc[_p("2025-01")] == pytest.approx(162.0)
        assert s.loc[_p("2025-02")] == pytest.approx(212.0)
        assert s.loc[_p("2025-03")] == pytest.approx(42.0)

    def test_returns_positive_magnitudes(self):
        s = monthly_outgo(sample_df())
        assert (s > 0).all()

    def test_excludes_transfers_and_income(self):
        # If Transfers/Income leaked in, 2025-01 would not be exactly 162.
        s = monthly_outgo(sample_df())
        assert s.loc[_p("2025-01")] == pytest.approx(162.0)

    def test_sorted_by_month(self):
        s = monthly_outgo(sample_df())
        assert list(s.index) == sorted(s.index)


class TestMonthlyByCategory:
    def test_pivot_cells(self):
        pivot = monthly_by_category(sample_df())
        assert pivot.loc[_p("2025-01"), "Groceries"] == pytest.approx(100.0)
        assert pivot.loc[_p("2025-02"), "Groceries"] == pytest.approx(200.0)
        assert pivot.loc[_p("2025-01"), "Subscriptions"] == pytest.approx(12.0)

    def test_missing_combo_is_zero_not_nan(self):
        pivot = monthly_by_category(sample_df())
        # No groceries in 2025-03
        assert pivot.loc[_p("2025-03"), "Groceries"] == 0

    def test_excludes_transfers_and_income_columns(self):
        pivot = monthly_by_category(sample_df())
        assert "Transfers" not in pivot.columns
        assert "Income" not in pivot.columns


class TestIncomeVsOutgo:
    def test_columns(self):
        out = income_vs_outgo(sample_df())
        assert set(["income", "outgo", "net"]).issubset(out.columns)

    def test_income_excludes_transfer_in(self):
        out = income_vs_outgo(sample_df())
        # 2025-02 has +1000 SCHWAB (Transfers) that must NOT count as income
        assert out.loc[_p("2025-02"), "income"] == pytest.approx(6000.0)

    def test_net_math(self):
        out = income_vs_outgo(sample_df())
        assert out.loc[_p("2025-01"), "net"] == pytest.approx(6000.0 - 162.0)
        assert out.loc[_p("2025-03"), "income"] == pytest.approx(0.0)
        assert out.loc[_p("2025-03"), "net"] == pytest.approx(-42.0)


class TestAverageMonthlyOutgo:
    def test_drops_first_and_last_by_default(self):
        # Only 2025-02 remains -> average is that month's outgo, 212.
        assert average_monthly_outgo(sample_df()) == pytest.approx(212.0)

    def test_keep_all_months(self):
        avg = average_monthly_outgo(sample_df(), exclude_first=False, exclude_last=False)
        assert avg == pytest.approx((162.0 + 212.0 + 42.0) / 3)


class TestDetectRecurring:
    def test_finds_stable_monthly_subscription(self):
        rec = detect_recurring(sample_df(), min_months=3)
        assert "ADOBE" in set(rec["merchant"])

    def test_excludes_below_threshold_merchants(self):
        rec = detect_recurring(sample_df(), min_months=3)
        merchants = set(rec["merchant"])
        assert "VONS" not in merchants          # only 2 months
        assert "IRVSBURGERS" not in merchants   # only 2 months

    def test_columns_and_annualized(self):
        rec = detect_recurring(sample_df(), min_months=3)
        assert set(
            ["merchant", "category", "months_seen", "monthly_amount", "annualized"]
        ).issubset(rec.columns)
        adobe = rec[rec["merchant"] == "ADOBE"].iloc[0]
        assert adobe["months_seen"] == 3
        assert adobe["monthly_amount"] == pytest.approx(12.0)
        assert adobe["annualized"] == pytest.approx(144.0)

    def test_sorted_by_annualized_desc(self):
        rec = detect_recurring(sample_df(), min_months=1)  # loosen so >1 row exists
        assert list(rec["annualized"]) == sorted(rec["annualized"], reverse=True)
