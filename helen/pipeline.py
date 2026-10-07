"""Side-effecting orchestration module. This will replace the 'uncategorized.py' code
and will allow notebooks to drive imperative operations or create visualizations"""
import logging
import pandas as pd

from helen.identity import assign_txn_ids
from helen.reconcile import reconcile, parse_control_totals
from helen.store import read_transactions, upsert_transactions
from helen.visa_load import load_pdf_pages
from helen.visa_parse import parse_statement
from helen.load import load_raw, load_category_rules, load_check_notes
from helen.clean import clean
from helen.categorize import categorize
from helen.enrich import apply_check_notes

logger = logging.getLogger(__name__)

def build_visa_dataframe(pdf_paths):
    """Parse and categorize Visa PDFs into frame. Side-effecting, obviously"""
    rules = load_category_rules()
    frames = []

    for p in pdf_paths:
        pages = load_pdf_pages(p)
        df = categorize(parse_statement(pages), rules)
        frames.append(df)

        # if we found discrepancies, issue a warning, don't throw
        discrepancies = reconcile(df, parse_control_totals(pages))
        for d in discrepancies:
            logger.warning("reconcile %s: expected %.2f, got %.2f (delta %.2f) in %s", 
                           d.check, d.expected, d.actual, d.delta, p)
    return pd.concat(frames, ignore_index=True)


def build_dataframe(csv_path):
    """Load & clean & categorize & enrich.
    Generate DataFrame ready for analysis or visualizations.
    Side-effecting -> reads CSV and YAML config."""
    loaded = clean(load_raw(csv_path))
    categorized= categorize(loaded, load_category_rules())
    df = apply_check_notes(categorized, load_check_notes())
    return df


def build_combined(csv_path, pdf_paths):
    """Checking & Visa in one frame, with a 'source' column.
    De-dupes nothing, relies on card payments being categorized
    as Transfers"""
    checking = build_dataframe(csv_path).assign(source="checking")
    visa = build_visa_dataframe(pdf_paths)
    return pd.concat([checking, visa], ignore_index=True)


def ingest_checking(con, csv_path):
    df = assign_txn_ids(build_dataframe(csv_path).assign(source="checking"), "checking")
    return upsert_transactions(con, df.assign(source_file=str(csv_path)))


def ingest_visa(con, pdf_path):
    df = assign_txn_ids(build_visa_dataframe([pdf_path]), "visa")
    return upsert_transactions(con, df.assign(source_file=str(pdf_path)))


def load_analysis_frame(con):
    """Notebook calls this instead of build_dataframe/build_combined.
    Reads the store, then rehydrates the derived columns that analyze.py
    expects (the store keeps only the minimal neutral columns), and
    re-derives categories from the YAML rules file."""
    df = read_transactions(con)
    # SQLite stores minimal/neutral types; rebuild the clean() shape:
    df["date"] = pd.to_datetime(df["date"])          # ISO string -> datetime
    df["month"] = df["date"].dt.to_period("M")       # analyze groups/pivots on this
    df["is_outflow"] = df["is_outflow"].astype(bool)  # int 0/1 -> bool for masking
    return categorize(df, load_category_rules())
