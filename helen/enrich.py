import pandas as pd
import logging

logger = logging.getLogger(__name__)


def apply_check_notes(df: pd.DataFrame, notes: dict):
    """Context: WF CSVs only list checks as 'CHECK'
    To get information about who/what etc. you need to add 
    check metadata to the config file. Cumbersome but repeatable.
    This fn applies that metadata with some mild checks for missing
    or conflicting fields."""
    out = df.copy()
    for check_number, info in notes.items():
        mask = out["check_no"] == str(check_number)

        # guard against deltas btwn CSV and check metadata YAML
        if "amount" in info:
            actual = out.loc[mask, "amount"]
            mismatched = actual[(actual - info["amount"]).abs() > 0.1]
            if not mismatched.empty:
                logger.warning( 
                    "check number %s data amount %s != info amount %s",
                    check_number, list(mismatched), info["amount"]
                )

        out.loc[mask, "merchant"] = info["payee"]
        out.loc[mask, "category"] = info["category"]
    return out
