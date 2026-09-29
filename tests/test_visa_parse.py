"""Tests for the (pure) Visa statement parser: helen/visa_parse.py

------------------------------------------------------------------------------
HOW SECTION STATE WORKS  (this is the bit that was confusing)
------------------------------------------------------------------------------
A Visa statement is a flat list of text lines. Some lines are *section headers*:

    Other Credits                                <- flips state to "credits"
    4998 05/20 05/21 ... DSW ...        66.44    <- a credit  (money IN, +)
    TOTAL OTHER CREDITS FOR THIS PERIOD $178.58
    Purchases, Balance Transfers & Other Charges <- flips state to "charges"
    4998 05/12 05/14 ... FHDA FUEL ...  91.24    <- a charge  (money OUT, -)
    Interest Charged                             <- flips state to "interest"
    INTEREST CHARGE ON PURCHASES         0.00    <- not a transaction

No individual transaction line says whether it's a credit or a charge. You only
know by remembering which header you last passed. So the parser walks the page
top-to-bottom carrying a `section` accumulator:

    section = None
    for line in page_lines:
        section = classify_section(line, section)   # header? -> new state, else unchanged
        row = parse_line(line, section)             # uses section to set the sign
        if row: rows.append(row)

That's the whole trick. `classify_section` is the ONLY thing that changes the
state; `parse_line` just *reads* it to decide the sign (+ for credits, - for
charges, and None/skip for anything else).

------------------------------------------------------------------------------
API these tests expect you to build in helen/visa_parse.py
------------------------------------------------------------------------------
    ROW: re.Pattern
        Matches a transaction line: card | trans MM/DD | post MM/DD | ref | desc | amt

    classify_section(line: str, current: str | None) -> str | None
        If `line` is a section header, return the new section key
        ("credits" | "charges" | "interest"). Otherwise return `current` unchanged.

    parse_amount(raw: str) -> float
        "14,719.02" -> 14719.02  (strip thousands separators)

    extract_visa_merchant(desc: str) -> str
        Clean a Visa description into a merchant name (uppercased). Strips a
        trailing 2-letter state, a leading "PAYPAL *", phone numbers, etc.

    parse_line(line: str, section: str | None) -> dict | None
        Returns None unless `line` matches ROW *and* section is a capturing
        section ("credits"/"charges"). On a match returns a dict with at least:
            {"trans": "05/20", "post": "05/21", "merchant": "...",
             "merchant_raw": "<original desc>", "amount": <signed float>,
             "is_outflow": <bool>}
        Sign: charges -> negative, credits -> positive.

    infer_year(trans_mmdd: str, period_start: date, period_end: date) -> int
        Transaction dates are MM/DD with no year. Pick the year from the
        statement period. If the period straddles a year boundary, months >=
        period_start's month belong to period_start.year, else period_end.year.

    parse_statement(pages: list[str]) -> pd.DataFrame
        Full parse of one statement (list of per-page text). Emits the same tidy
        columns clean.clean() produces, plus source="visa":
            date, month, amount, is_outflow, txn_type, merchant_raw,
            merchant, check_no, source
"""
from datetime import date

import pandas as pd
import pytest

from helen.visa_parse import (
    classify_section,
    parse_amount,
    extract_visa_merchant,
    parse_line,
    infer_year,
    parse_statement,
)

# --- real lines lifted from the actual PDFs, safe to hard-code as fixtures ----
CREDIT_ROW = "4998 05/20 05/21 7406726GXN20KK6J4 DSW29496 PLEASANT HILL PLEASANT HILL CA 66.44"
CASH_BACK_ROW = "4998 08/01 08/04 7446539K87EKH47KQ CASH BACK REDEMPTION REF 206052971 283.50"
PAYPAL_CREDIT_ROW = "4998 05/26 05/27 7402762H21Z08RMKY PAYPAL *KOHL S INC 402-935-7733 WI 7.63"
CHARGE_ROW = "4998 05/12 05/14 2442733GM3FRA2T6R FHDA FUEL INC ALAMEDA CA 91.24"
BIG_CHARGE_ROW = "4998 06/06 06/06 7549096HE0XSLLT0K ONLINE PAYMENT THANK YOU 14,719.02"

COLUMN_HEADER = "Card Trans Post Reference Number Description Credits Charges"
INTEREST_LINE = "INTEREST CHARGE ON PURCHASES 0.00"
BLANK = "   "


# ============================================================================
# classify_section  -- the ONLY thing that changes the section state
# ============================================================================
class TestClassifySection:
    def test_credits_header_sets_credits(self):
        assert classify_section("Other Credits", None) == "credits"

    def test_charges_header_sets_charges(self):
        line = "Purchases, Balance Transfers & Other Charges"
        assert classify_section(line, "credits") == "charges"

    def test_interest_header_sets_interest(self):
        assert classify_section("Interest Charged", "charges") == "interest"

    def test_transaction_line_leaves_state_unchanged(self):
        # a normal txn row is NOT a header -> the accumulator must pass through
        assert classify_section(CHARGE_ROW, "charges") == "charges"

    def test_column_header_is_not_a_section_header(self):
        # the repeated "Card Trans Post ..." line must not flip state
        assert classify_section(COLUMN_HEADER, "charges") == "charges"

    def test_unrelated_line_passes_state_through(self):
        assert classify_section("Account ending in 4998", "credits") == "credits"


# ============================================================================
# parse_amount  -- thousands separators
# ============================================================================
class TestParseAmount:
    def test_plain(self):
        assert parse_amount("91.24") == pytest.approx(91.24)

    def test_with_comma(self):
        assert parse_amount("14,719.02") == pytest.approx(14719.02)


# ============================================================================
# extract_visa_merchant  -- Visa descriptions differ from checking's format
# ============================================================================
class TestExtractVisaMerchant:
    def test_strips_trailing_state(self):
        m = extract_visa_merchant("FHDA FUEL INC ALAMEDA CA")
        assert m == m.upper()
        assert not m.endswith(" CA")
        assert "FHDA FUEL" in m

    def test_strips_paypal_prefix(self):
        # PayPal hides the real merchant behind "PAYPAL *"
        m = extract_visa_merchant("PAYPAL *KOHL S INC 402-935-7733 WI")
        assert "KOHL" in m
        assert "PAYPAL" not in m

    def test_cash_back_redemption_survives(self):
        # no city/state tail, has a REF number -> must not be over-stripped
        m = extract_visa_merchant("CASH BACK REDEMPTION REF 206052971")
        assert "CASH BACK REDEMPTION" in m


# ============================================================================
# parse_line  -- READS the section state to decide the sign
# ============================================================================
class TestParseLine:
    def test_charge_is_negative(self):
        row = parse_line(CHARGE_ROW, "charges")
        assert row is not None
        assert row["amount"] == pytest.approx(-91.24)
        assert row["is_outflow"] is True

    def test_credit_is_positive(self):
        row = parse_line(CREDIT_ROW, "credits")
        assert row is not None
        assert row["amount"] == pytest.approx(66.44)
        assert row["is_outflow"] is False

    def test_cash_back_credit_is_positive(self):
        row = parse_line(CASH_BACK_ROW, "credits")
        assert row is not None
        assert row["amount"] == pytest.approx(283.50)

    def test_same_row_flips_sign_with_section(self):
        # THE key point: identical line, opposite sign, purely from section state
        as_charge = parse_line(CREDIT_ROW, "charges")["amount"]
        as_credit = parse_line(CREDIT_ROW, "credits")["amount"]
        assert as_charge == pytest.approx(-as_credit)

    def test_comma_amount_parsed(self):
        row = parse_line(BIG_CHARGE_ROW, "charges")
        assert row["amount"] == pytest.approx(-14719.02)

    def test_keeps_raw_description(self):
        row = parse_line(CHARGE_ROW, "charges")
        assert "FHDA FUEL INC ALAMEDA CA" in row["merchant_raw"]

    def test_column_header_returns_none(self):
        assert parse_line(COLUMN_HEADER, "charges") is None

    def test_interest_line_returns_none(self):
        assert parse_line(INTEREST_LINE, "interest") is None

    def test_blank_returns_none(self):
        assert parse_line(BLANK, "charges") is None

    def test_txn_line_in_noncapturing_section_returns_none(self):
        # even a valid-looking row must be ignored under "interest" / None
        assert parse_line(CHARGE_ROW, "interest") is None
        assert parse_line(CHARGE_ROW, None) is None


# ============================================================================
# infer_year  -- MM/DD dates + statement period, incl. Dec->Jan rollover
# ============================================================================
class TestInferYear:
    def test_within_single_year(self):
        start, end = date(2026, 5, 14), date(2026, 6, 12)
        assert infer_year("05/20", start, end) == 2026
        assert infer_year("06/12", start, end) == 2026

    def test_rollover_december_belongs_to_start_year(self):
        start, end = date(2025, 12, 14), date(2026, 1, 13)
        assert infer_year("12/28", start, end) == 2025

    def test_rollover_january_belongs_to_end_year(self):
        start, end = date(2025, 12, 14), date(2026, 1, 13)
        assert infer_year("01/05", start, end) == 2026


# ============================================================================
# parse_statement  -- threads section state down the page, end to end
# ============================================================================
# A faithful mini-statement: header lines, a credits block, a charges block,
# and an interest block that must be ignored.
FAKE_PAGE = "\n".join(
    [
        "SIGNATURE",
        "Account ending in 4998",
        "Statement Period 05/14/2026 to 06/12/2026",
        "Page 2 of 5",
        "Card Trans Post Reference Number Description Credits Charges",
        "Other Credits",
        CREDIT_ROW,           # +66.44
        PAYPAL_CREDIT_ROW,    # +7.63
        "TOTAL OTHER CREDITS FOR THIS PERIOD $74.07",
        "Purchases, Balance Transfers & Other Charges",
        CHARGE_ROW,           # -91.24
        "Interest Charged",
        INTEREST_LINE,        # ignored
        "TOTAL INTEREST CHARGED FOR THIS PERIOD $0.00",
    ]
)

TIDY_COLUMNS = {
    "date", "month", "amount", "is_outflow",
    "txn_type", "merchant_raw", "merchant", "check_no", "source",
}


class TestParseStatement:
    @pytest.fixture
    def df(self):
        return parse_statement([FAKE_PAGE])

    def test_row_count_excludes_headers_and_interest(self, df):
        # 2 credits + 1 charge = 3 real transactions
        assert len(df) == 3

    def test_sign_split(self, df):
        assert (df["amount"] > 0).sum() == 2   # the two credits
        assert (df["amount"] < 0).sum() == 1   # the one charge

    def test_source_tag(self, df):
        assert (df["source"] == "visa").all()

    def test_columns_match_clean_schema(self, df):
        assert TIDY_COLUMNS.issubset(set(df.columns))

    def test_year_applied_from_statement_period(self, df):
        assert (pd.to_datetime(df["date"]).dt.year == 2026).all()

    def test_credit_total_reconciles_to_printed_total(self, df):
        # statement prints TOTAL OTHER CREDITS = 74.07; parsed credits must match
        parsed = df.loc[df["amount"] > 0, "amount"].sum()
        assert parsed == pytest.approx(74.07)
