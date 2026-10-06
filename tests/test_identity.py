"""Tests for the (pure) transaction-identity layer: helen/identity.py

------------------------------------------------------------------------------
WHY THIS MODULE EXISTS
------------------------------------------------------------------------------
Appends are only safe if every transaction has a stable id, so re-ingesting a
month is a no-op (INSERT OR IGNORE skips rows it already has). Two sources, two
strategies:

  * Visa  -> the statement prints a unique Reference Number. visa_txn_id just
             normalizes/passes it through.
  * Checking -> no id in the CSV. Build a deterministic sha1 hash of the row's
             own values (date | amount | description). But identical values can
             legitimately repeat (two $5 coffees, same day), so fold in an
             "occurrence ordinal" (0,1,2,... within the file) to keep real
             duplicates distinct while still collapsing an accidental re-ingest.

------------------------------------------------------------------------------
API these tests expect in helen/identity.py
------------------------------------------------------------------------------
    checking_txn_id(date, amount, description, occurrence: int) -> str
        Deterministic 40-char sha1 hexdigest. MUST include `occurrence` in the
        key so repeats get different ids.

    visa_txn_id(reference: str) -> str
        Stable id from the printed Reference Number (strip/normalize, no hashing
        required).

    assign_txn_ids(df: pd.DataFrame, source: str) -> pd.DataFrame
        Returns a copy with a `txn_id` column added (does not mutate input).
        - source == "checking": hash date|amount|merchant_raw, with the
          occurrence ordinal via groupby(...).cumcount().
        - source == "visa": txn_id = visa_txn_id(row["reference"]).
"""
import pandas as pd
import pytest

from helen.identity import checking_txn_id, visa_txn_id, assign_txn_ids


# ============================================================================
# checking_txn_id -- deterministic hash that INCLUDES occurrence
# ============================================================================
class TestCheckingTxnId:
    def test_returns_hex_string(self):
        tid = checking_txn_id("2026-09-14", -5.00, "BLUE BOTTLE", 0)
        assert isinstance(tid, str)
        assert len(tid) == 40                     # sha1 hexdigest length
        assert all(c in "0123456789abcdef" for c in tid)

    def test_is_deterministic(self):
        a = checking_txn_id("2026-09-14", -5.00, "BLUE BOTTLE", 0)
        b = checking_txn_id("2026-09-14", -5.00, "BLUE BOTTLE", 0)
        assert a == b

    def test_occurrence_changes_the_id(self):
        # the whole point of the ordinal: same values, different occurrence -> different id
        first = checking_txn_id("2026-09-14", -5.00, "BLUE BOTTLE", 0)
        second = checking_txn_id("2026-09-14", -5.00, "BLUE BOTTLE", 1)
        assert first != second

    def test_different_fields_change_the_id(self):
        base = checking_txn_id("2026-09-14", -5.00, "BLUE BOTTLE", 0)
        assert checking_txn_id("2026-09-15", -5.00, "BLUE BOTTLE", 0) != base
        assert checking_txn_id("2026-09-14", -6.00, "BLUE BOTTLE", 0) != base
        assert checking_txn_id("2026-09-14", -5.00, "PEETS", 0) != base


# ============================================================================
# visa_txn_id -- stable passthrough of the printed Reference Number
# ============================================================================
class TestVisaTxnId:
    def test_is_deterministic(self):
        assert visa_txn_id("7406726GXN20KK6J4") == visa_txn_id("7406726GXN20KK6J4")

    def test_distinct_references_distinct_ids(self):
        assert visa_txn_id("7406726GXN20KK6J4") != visa_txn_id("2442733GM3FRA2T6R")

    def test_normalizes_whitespace(self):
        # tolerate stray surrounding whitespace from extraction
        assert visa_txn_id("  7406726GXN20KK6J4 ") == visa_txn_id("7406726GXN20KK6J4")


# ============================================================================
# assign_txn_ids -- adds a txn_id column; the two guarantees that matter
# ============================================================================
class TestAssignTxnIdsChecking:
    @pytest.fixture
    def dupes(self):
        # two genuinely identical same-day transactions
        return pd.DataFrame(
            {
                "date": ["2026-09-14", "2026-09-14"],
                "amount": [-5.00, -5.00],
                "merchant_raw": ["BLUE BOTTLE", "BLUE BOTTLE"],
            }
        )

    def test_adds_txn_id_column_without_mutating_input(self, dupes):
        before = dupes.copy()
        out = assign_txn_ids(dupes, "checking")
        assert "txn_id" in out.columns
        assert "txn_id" not in dupes.columns          # original untouched
        pd.testing.assert_frame_equal(dupes, before)

    def test_identical_rows_get_distinct_ids(self, dupes):
        # GUARANTEE 1: real duplicates are kept distinct (via the occurrence ordinal)
        out = assign_txn_ids(dupes, "checking")
        assert out["txn_id"].nunique() == 2

    def test_reingesting_same_frame_is_idempotent(self, dupes):
        # GUARANTEE 2: same file parsed again -> same ids (so INSERT OR IGNORE skips)
        first = assign_txn_ids(dupes, "checking")["txn_id"].tolist()
        second = assign_txn_ids(dupes, "checking")["txn_id"].tolist()
        assert first == second

    def test_distinct_rows_get_distinct_ids(self):
        df = pd.DataFrame(
            {
                "date": ["2026-09-14", "2026-09-15"],
                "amount": [-5.00, -12.00],
                "merchant_raw": ["BLUE BOTTLE", "SAFEWAY"],
            }
        )
        out = assign_txn_ids(df, "checking")
        assert out["txn_id"].nunique() == 2


class TestAssignTxnIdsVisa:
    def test_uses_reference_number(self):
        df = pd.DataFrame(
            {
                "reference": ["7406726GXN20KK6J4", "2442733GM3FRA2T6R"],
                "amount": [66.44, -91.24],
                "merchant_raw": ["DSW29496", "FHDA FUEL INC"],
            }
        )
        out = assign_txn_ids(df, "visa")
        assert out["txn_id"].tolist() == [
            visa_txn_id("7406726GXN20KK6J4"),
            visa_txn_id("2442733GM3FRA2T6R"),
        ]
