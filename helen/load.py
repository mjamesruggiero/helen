import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

RAW_COLUMNS = ["DATE", "DESCRIPTION", "AMOUNT", "CHECK #", "STATUS"]

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



