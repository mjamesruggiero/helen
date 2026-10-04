"""Side-effecting orchestration module. This will replace the 'uncategorized.py' code
and will allow notebooks to drive imperative operations or create visualizations"""
import logging

import pandas as pd
from helen.visa_load import load_pdf_pages
from helen.visa_parse import parse_statement


logger = logging.getLogger(__name__)
from helen.load import load_raw, load_category_rules, load_check_notes
from helen.clean import clean
from helen.categorize import categorize
from helen.enrich import apply_check_notes

def build_visa_dataframe(pdf_paths):
    """Parse and categorize Visa PDFs into frame. Side-effecting, obviously"""
    rules = load_category_rules()
    frames = [categorize(parse_statement(load_pdf_pages(p)), rules) for p in pdf_paths]
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
