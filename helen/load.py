import logging
from pathlib import Path
import pandas as pd
import yaml

logger = logging.getLogger(__name__)

RAW_COLUMNS = ["DATE", "DESCRIPTION", "AMOUNT", "CHECK #", "STATUS"]

# Personal categorization rules live OUTSIDE the repo (they get personal as you
# add merchants). Default location: ~/bin/helen_categories.yaml
DEFAULT_RULES_PATH = Path.home() / "bin" / "helen_categories.yaml"

def load_raw(csv_path: str | Path) -> pd.DataFrame:
    """Read the WF checking CSV into a raw dataframe.
        Side-effecting; touches the filesystem. Keep logic out."""
    path = Path(csv_path)
    logger.info("Rading checking CSV: %s", path)
    df = pd.read_csv(
        path, 
        dtype={"DESCRIPTION": "string", "CHECK #": "string", "STATUS": "string"}
    )

    missing = set(RAW_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing expected columns: {sorted(missing)}")

    posted = df[df["STATUS"] == "Posted"].copy()
    logger.info("Loaded %d rows (%d after Posted filter)", len(df), len(posted))
    return posted


def load_category_rules(yaml_path: str | Path = DEFAULT_RULES_PATH) -> dict[str, list[str]]:
    """Read the categories YAML (default: ~/bin/helen_categories.yaml).

    Kept out of the repo because the rules get personal. Side-effecting.
    """
    with open(yaml_path) as fh:
        cfg = yaml.safe_load(fh)
    return cfg["categories"]
