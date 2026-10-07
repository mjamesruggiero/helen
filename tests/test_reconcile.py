"""Tests for the (pure) reconciliation layer: helen/reconcile.py

------------------------------------------------------------------------------
purpose of reconcile.py
------------------------------------------------------------------------------
A future statement could change layout and silently drop a transaction row.
Reconcile catches that by comparing parsed rows against the control totals
the statement prints about itself. Two independent checks:

  A. row-vs-total     sum(credit rows)  == TOTAL OTHER CREDITS
                      sum(charge rows)  == TOTAL PURCHASES, BALANCE TRANSFERS...
  B. statement        Previous - Payments - OtherCredits + Purchases
     integrity          + Fees + Interest == New Balance   (verified to hold)

NOTE: parser intentionally OMITS "Payments" line (it's a transfer from
checking, not card spending); reconcile does NOT expect payments among the
rows -- it only reconciles credits and charges. Payments appear only inside the
balance-identity check, via the extracted total.
"""
import pandas as pd
import pytest

from helen.reconcile import Totals, Discrepancy, parse_control_totals, reconcile


# A summary block modeled on VISA_06_2026.pdf, including the traps:
#   - "New Balance" appears more than once
#   - a YTD interest/fees line (... IN 2026) that must NOT be read as the period figure
# fees and interest are deliberately NON-ZERO: the parser falls back to 0.0 when a
# pattern doesn't match, so a zero fixture would pass even with a broken regex.
# Balance identity (must hold, or every "clean" reconcile test fails):
#   11190.30 - 14719.02 - 178.58 + 5084.52 + 39.00 + 12.34 = 1428.56
SUMMARY_TEXT = "\n".join(
    [
        "Previous Balance $11,190.30 Total Credit Limit $25,500",
        "- Payments $14,719.02 Cash Advance Limit $5,100",
        "+ Purchases, Balance Transfers & $5,084.52",
        "+ Fees Charged $39.00",
        "+ Interest Charged $12.34",
        "= New Balance $1,428.56",
        "New Balance $1,428.56",
        "TOTAL PAYMENTS FOR THIS PERIOD $14,719.02",
        "TOTAL OTHER CREDITS FOR THIS PERIOD $178.58",
        "TOTAL PURCHASES, BALANCE TRANSFERS & OTHER CHARGES FOR THIS PERIOD $5,084.52",
        "TOTAL FEES CHARGED FOR THIS PERIOD $39.00",
        "TOTAL INTEREST CHARGED FOR THIS PERIOD $12.34",
        "TOTAL FEES CHARGED IN 2026 $78.00",        # YTD trap
        "TOTAL INTEREST CHARGED IN 2026 $154.46",   # YTD trap
    ]
)

# The totals those lines should yield (the source of truth for the row tests).
CLEAN_TOTALS = Totals(
    previous_balance=11190.30,
    payments=14719.02,
    other_credits=178.58,
    purchases=5084.52,
    fees=39.00,
    interest=12.34,
    new_balance=1428.56,
)


def _frame(amounts):
    """Minimal rows frame; reconcile only needs the signed `amount` column."""
    return pd.DataFrame({"amount": amounts})


def _by_check(discrepancies):
    return {d.check for d in discrepancies}


# ============================================================================
# parse_control_totals -- regex the printed $ figures out of the text
# ============================================================================
class TestParseControlTotals:
    @pytest.fixture
    def totals(self):
        return parse_control_totals([SUMMARY_TEXT])

    def test_extracts_each_field(self, totals):
        assert totals.previous_balance == pytest.approx(11190.30)
        assert totals.payments == pytest.approx(14719.02)
        assert totals.other_credits == pytest.approx(178.58)
        assert totals.purchases == pytest.approx(5084.52)
        assert totals.fees == pytest.approx(39.00)
        assert totals.new_balance == pytest.approx(1428.56)

    def test_period_interest_not_ytd(self, totals):
        # must read "FOR THIS PERIOD" ($12.34), not "IN 2026" ($154.46)
        assert totals.interest == pytest.approx(12.34)

    def test_period_fees_not_ytd(self, totals):
        # must read "FOR THIS PERIOD" ($39.00), not "IN 2026" ($78.00)
        assert totals.fees == pytest.approx(39.00)

    def test_strips_commas_and_dollar_signs(self, totals):
        # if commas/$ weren't handled, payments would not parse as a float
        assert isinstance(totals.payments, float)
        assert totals.payments == pytest.approx(14719.02)


# ============================================================================
# reconcile -- the whole point: catch dropped / mis-signed rows
# ============================================================================
class TestReconcileClean:
    def test_matching_rows_return_no_discrepancies(self):
        df = _frame([178.58, -5084.52])   # credits == 178.58, charges == 5084.52
        assert reconcile(df, CLEAN_TOTALS) == []

    def test_within_tolerance_is_clean(self):
        # off by half a cent -> still clean at tol=0.01
        df = _frame([178.585, -5084.52])
        assert reconcile(df, CLEAN_TOTALS) == []

    def test_split_rows_still_reconcile(self):
        # multiple credit + charge rows that sum to the totals
        df = _frame([66.44, 7.63, 45.00, 5.29, 54.22, -2000.00, -3084.52])
        assert reconcile(df, CLEAN_TOTALS) == []


class TestReconcileCatchesProblems:
    def test_dropped_charge_flags_charges(self):
        # a charge row went missing: charges now short by 84.52
        df = _frame([178.58, -5000.00])
        d = reconcile(df, CLEAN_TOTALS)
        assert _by_check(d) == {"charges"}
        (charges,) = [x for x in d if x.check == "charges"]
        assert charges.expected == pytest.approx(5084.52)
        assert charges.actual == pytest.approx(5000.00)
        assert charges.delta == pytest.approx(-84.52)

    def test_dropped_credit_flags_credits(self):
        df = _frame([100.00, -5084.52])   # credits short by 78.58
        d = reconcile(df, CLEAN_TOTALS)
        assert _by_check(d) == {"credits"}

    def test_mis_signed_row_flags_both_sides(self):
        # a credit (should be +178.58) got stored negative:
        # credits side loses it, charges side gains it -> both totals wrong
        df = _frame([-178.58, -5084.52])
        assert _by_check(reconcile(df, CLEAN_TOTALS)) == {"credits", "charges"}

    def test_broken_balance_identity_flags_identity_only(self):
        # rows still match credits/charges, but an extracted total is wrong
        bad = Totals(**{**CLEAN_TOTALS.__dict__, "new_balance": 9999.99})
        df = _frame([178.58, -5084.52])
        assert _by_check(reconcile(df, bad)) == {"balance_identity"}

    def test_returns_discrepancy_objects(self):
        df = _frame([178.58, -5000.00])
        d = reconcile(df, CLEAN_TOTALS)
        assert all(isinstance(x, Discrepancy) for x in d)
