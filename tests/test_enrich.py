"""Tests for helen.enrich — pure check-annotation enrichment.

TDD: these tests are the SPEC. Implement helen/enrich.py until they pass.

    pytest "tests/test_enrich.py::TestApplyCheckNotes" -v
    pytest "tests/test_enrich.py::TestAmountMismatchWarning" -v

`apply_check_notes(df, notes)` takes the categorized tidy frame plus the check-notes
dict (from load_check_notes) and, for each check_no in notes, overwrites that row's
`merchant` and `category`. It must not mutate the input.
"""
import logging

import pandas as pd
import pytest

from helen.enrich import apply_check_notes


NOTES = {
    "2661": {"payee": "Mary Millosovich — home repairs", "category": "HomeRepair", "amount": -5000.00},
    "2663": {"payee": "MRI lab — medical testing",       "category": "Medical",    "amount": -710.36},
    "9999": {"payee": "Not in data",                     "category": "Ghost",      "amount": -1.00},
}


def sample_df() -> pd.DataFrame:
    """Two checks + one non-check row.

    Only 2661 and 2663 exist in the data; note 9999 has no matching row (no-op).
    The non-check row (VONS) must be left untouched.
    """
    return pd.DataFrame(
        {
            "merchant":  ["CHECK", "CHECK", "VONS"],
            "category":  ["Uncategorized", "Uncategorized", "Groceries"],
            "check_no":  ["2661", "2663", ""],
            "amount":    [-5000.00, -710.36, -67.22],
            "txn_type":  ["CHECK", "CHECK", "PURCHASE"],
        }
    )


class TestApplyCheckNotes:
    def test_overwrites_merchant(self):
        out = apply_check_notes(sample_df(), NOTES)
        assert out.loc[0, "merchant"] == "Mary Millosovich — home repairs"
        assert out.loc[1, "merchant"] == "MRI lab — medical testing"

    def test_overwrites_category(self):
        out = apply_check_notes(sample_df(), NOTES)
        assert out.loc[0, "category"] == "HomeRepair"
        assert out.loc[1, "category"] == "Medical"

    def test_leaves_non_check_rows_untouched(self):
        out = apply_check_notes(sample_df(), NOTES)
        assert out.loc[2, "merchant"] == "VONS"
        assert out.loc[2, "category"] == "Groceries"

    def test_note_with_no_matching_row_is_noop(self):
        # 9999 isn't in the data; should not raise and should add no rows
        out = apply_check_notes(sample_df(), NOTES)
        assert len(out) == 3

    def test_does_not_mutate_input(self):
        df = sample_df()
        _ = apply_check_notes(df, NOTES)
        assert df.loc[0, "merchant"] == "CHECK"
        assert df.loc[0, "category"] == "Uncategorized"

    def test_empty_notes_is_noop(self):
        out = apply_check_notes(sample_df(), {})
        assert list(out["merchant"]) == ["CHECK", "CHECK", "VONS"]


class TestAmountMismatchWarning:
    def test_warns_when_amount_disagrees(self, caplog):
        df = sample_df()
        # Corrupt the data amount for check 2661 so it disagrees with the note.
        df.loc[0, "amount"] = -4200.00
        with caplog.at_level(logging.WARNING):
            out = apply_check_notes(df, NOTES)
        # Annotation still applied...
        assert out.loc[0, "category"] == "HomeRepair"
        # ...but a warning was logged mentioning the check number.
        assert any("2661" in rec.message for rec in caplog.records)

    def test_no_warning_when_amounts_match(self, caplog):
        with caplog.at_level(logging.WARNING):
            apply_check_notes(sample_df(), NOTES)
        assert not any("2661" in rec.message for rec in caplog.records)

    def test_no_warning_when_note_has_no_amount(self, caplog):
        notes = {"2661": {"payee": "X", "category": "HomeRepair"}}  # no 'amount' key
        with caplog.at_level(logging.WARNING):
            apply_check_notes(sample_df(), notes)
        assert not any("2661" in rec.message for rec in caplog.records)
