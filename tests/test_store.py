"""Tests for the SQLite store: helen/store.py

Thin I/O layer, so we test it against an in-memory database (sqlite3.connect
":memory:"). Test idempotency guarantee: upserting the same rows twice does not duplicate;
that's the reason the recurring pipeline is safe.

store does NOT assign txn_ids (that's helen/identity.py). So these fixtures
hand it frames that already carry a txn_id, matching store.COLUMNS.
"""
import sqlite3

import pandas as pd
import pytest

from helen import store


def _tidy_frame(rows):
    """Build a frame with exactly the columns store.convert_to_rows expects."""
    return pd.DataFrame(rows, columns=store.COLUMNS)


TWO_ROWS = _tidy_frame(
    [
        ("id-a", "2026-09-14", -5.00, "BLUE BOTTLE", "BLUE BOTTLE",
         True, "PURCHASE", "", "checking", "data/raw/2026_09.csv"),
        ("id-b", "2026-09-15", -12.00, "SAFEWAY", "SAFEWAY",
         True, "PURCHASE", "", "checking", "data/raw/2026_09.csv"),
    ]
)


@pytest.fixture
def con():
    """Fresh in-memory DB with the schema created."""
    c = sqlite3.connect(":memory:")
    store.init_db(c)
    yield c
    c.close()


class TestRoundTrip:
    def test_insert_then_read_returns_all_rows(self, con):
        inserted = store.upsert_transactions(con, TWO_ROWS)
        assert inserted == 2
        back = store.read_transactions(con)
        assert len(back) == 2
        assert set(back["txn_id"]) == {"id-a", "id-b"}

    def test_read_on_empty_db_is_empty(self, con):
        back = store.read_transactions(con)
        assert len(back) == 0


class TestIdempotency:
    def test_second_upsert_inserts_zero(self, con):
        # GUARANTEE: re-ingesting the same month is a no-op
        assert store.upsert_transactions(con, TWO_ROWS) == 2
        assert store.upsert_transactions(con, TWO_ROWS) == 0

    def test_table_has_no_duplicates_after_double_upsert(self, con):
        store.upsert_transactions(con, TWO_ROWS)
        store.upsert_transactions(con, TWO_ROWS)
        back = store.read_transactions(con)
        assert len(back) == 2                      # not 4

    def test_overlapping_batches_merge_on_txn_id(self, con):
        # month 1 and a month-2 batch that re-includes a boundary row (id-b)
        store.upsert_transactions(con, TWO_ROWS)
        month2 = _tidy_frame(
            [
                ("id-b", "2026-09-15", -12.00, "SAFEWAY", "SAFEWAY",
                 True, "PURCHASE", "", "checking", "data/raw/2026_10.csv"),   # dup
                ("id-c", "2026-10-02", -8.00, "PEETS", "PEETS",
                 True, "PURCHASE", "", "checking", "data/raw/2026_10.csv"),   # new
            ]
        )
        assert store.upsert_transactions(con, month2) == 1   # only id-c is new
        assert set(store.read_transactions(con)["txn_id"]) == {"id-a", "id-b", "id-c"}


class TestTypeCoercion:
    def test_is_outflow_stored_as_int(self, con):
        store.upsert_transactions(con, TWO_ROWS)
        back = store.read_transactions(con)
        # SQLite has no bool; it must come back as 0/1 ints
        assert set(back["is_outflow"].unique()).issubset({0, 1})

    def test_date_stored_as_iso_string(self, con):
        store.upsert_transactions(con, TWO_ROWS)
        back = store.read_transactions(con)
        assert back["date"].tolist() == ["2026-09-14", "2026-09-15"]

    def test_accepts_timestamp_dates(self, con):
        # convert_to_rows runs pd.to_datetime, so a Timestamp column must survive
        frame = TWO_ROWS.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        assert store.upsert_transactions(con, frame) == 2
        assert store.read_transactions(con)["date"].tolist() == [
            "2026-09-14", "2026-09-15",
        ]
