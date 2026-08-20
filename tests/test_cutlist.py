"""Tests for the cut-list functions in helen.analyze.

TDD spec. Implement `category_trends` and `build_cut_list` until green:

    pytest "tests/test_cutlist.py::TestCategoryTrends" -v
    pytest "tests/test_cutlist.py::TestBuildCutList" -v
"""
import pandas as pd
import pytest

from helen.analyze import category_trends, build_cut_list


def _p(ym: str) -> pd.Period:
    return pd.Period(ym, freq="M")


class TestCategoryTrends:
    """`category_trends(df, recent=3) -> DataFrame` (index=category).

    Drops the partial first & last months, then compares the mean of the last
    `recent` months to the mean of the earlier months.
    """

    def _df(self):
        # 6 months so that after dropping first(01) & last(06) we have 02..05.
        # With recent=2: recent = {04,05}, prior = {02,03}.
        rows = [
            # month,     merchant, amount, category
            ("2025-01", "IRV",  -100.0, "Dining"),     # dropped (partial)
            ("2025-02", "IRV",   -10.0, "Dining"),
            ("2025-03", "IRV",   -20.0, "Dining"),
            ("2025-04", "IRV",   -40.0, "Dining"),
            ("2025-05", "IRV",   -60.0, "Dining"),
            ("2025-06", "IRV",  -999.0, "Dining"),     # dropped (partial)
            ("2025-01", "VONS", -100.0, "Groceries"),  # dropped
            ("2025-02", "VONS", -100.0, "Groceries"),
            ("2025-03", "VONS", -100.0, "Groceries"),
            ("2025-04", "VONS",  -80.0, "Groceries"),
            ("2025-05", "VONS",  -60.0, "Groceries"),
            ("2025-06", "VONS", -100.0, "Groceries"),  # dropped
        ]
        df = pd.DataFrame(rows, columns=["month", "merchant", "amount", "category"])
        df["month"] = df["month"].map(_p)
        df["is_outflow"] = df["amount"] < 0
        return df

    def test_recent_and_prior_averages(self):
        t = category_trends(self._df(), recent=2)
        # Dining: prior {10,20}=15, recent {40,60}=50
        assert t.loc["Dining", "prior_avg"] == pytest.approx(15.0)
        assert t.loc["Dining", "recent_avg"] == pytest.approx(50.0)
        # Groceries: prior {100,100}=100, recent {80,60}=70
        assert t.loc["Groceries", "prior_avg"] == pytest.approx(100.0)
        assert t.loc["Groceries", "recent_avg"] == pytest.approx(70.0)

    def test_delta_and_pct_change(self):
        t = category_trends(self._df(), recent=2)
        assert t.loc["Dining", "delta"] == pytest.approx(35.0)
        assert t.loc["Dining", "pct_change"] == pytest.approx(35.0 / 15.0)
        assert t.loc["Groceries", "delta"] == pytest.approx(-30.0)

    def test_sorted_by_delta_descending(self):
        t = category_trends(self._df(), recent=2)
        # Dining (+35) should come before Groceries (-30)
        assert list(t.index) == ["Dining", "Groceries"]


class TestBuildCutList:
    """`build_cut_list(df, ...) -> DataFrame`.

    Built on detect_recurring; adds a suggested_action per category and sorts by
    annualized cost descending.
    """

    def _df(self):
        rows = []
        for m in ["2025-01", "2025-02", "2025-03"]:
            rows += [
                (m, "ADOBE", -12.0, "Subscriptions"),
                (m, "EBMUD", -100.0, "Utilities"),
            ]
        # VONS: stable-ish groceries, 3 months -> also "recurring", default action
        rows += [
            ("2025-01", "VONS", -54.0, "Groceries"),
            ("2025-02", "VONS", -55.0, "Groceries"),
            ("2025-03", "VONS", -56.0, "Groceries"),
        ]
        df = pd.DataFrame(rows, columns=["month", "merchant", "amount", "category"])
        df["month"] = df["month"].map(_p)
        df["is_outflow"] = df["amount"] < 0
        return df

    def test_has_suggested_action_column(self):
        cut = build_cut_list(self._df(), min_months=3)
        assert "suggested_action" in cut.columns

    def test_action_by_category(self):
        cut = build_cut_list(self._df(), min_months=3).set_index("merchant")
        assert cut.loc["ADOBE", "suggested_action"] == "review / cancel"
        assert cut.loc["EBMUD", "suggested_action"] == "negotiate / downgrade"
        # Groceries isn't a special category -> default action
        assert cut.loc["VONS", "suggested_action"] == "review"

    def test_sorted_by_annualized_desc(self):
        cut = build_cut_list(self._df(), min_months=3)
        assert list(cut["annualized"]) == sorted(cut["annualized"], reverse=True)
        # EBMUD ($1200/yr) should top ADOBE ($144/yr)
        assert cut.iloc[0]["merchant"] == "EBMUD"
