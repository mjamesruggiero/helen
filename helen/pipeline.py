"""Side-effecting orchestration module. This will replace the 'uncategorized.py' code
and will allow notebooks to drive imperative operations or create visualizations"""
import logging


logger = logging.getLogger(__name__)
from helen.load import load_raw, load_category_rules, load_check_notes
from helen.clean import clean
from helen.categorize import categorize
from helen.enrich import apply_check_notes

def build_dataframe(csv_path):
    """Load & clean & categorize & enrich.
    Generate DataFrame ready for analysis or visualizations.
    Side-effecting -> reads CSV and YAML config."""
    loaded = clean(load_raw(csv_path))
    categorized= categorize(loaded, load_category_rules())
    df = apply_check_notes(categorized, load_check_notes())
    return df

