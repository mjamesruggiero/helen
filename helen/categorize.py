import pandas as pd


def categorize_merchant(merchant: str, category_rules: dict[str, list[str]]) -> str:
    """First category whose any substring appears in `merchant` (case-insensitive).
    No match? "Uncategorized."
    """
    m = merchant.upper()
    for category, needles in category_rules.items():
        if any(needle.upper() in m for needle in needles):
            return category
    return "Uncategorized"
    

def categorize(df: pd.DataFrame, category_rules: dict[str, list[str]]) -> pd.DataFrame:
    """Add a 'category' column via categorize_merchant. Does not mutate df"""
    out = df.copy()
    out["category"] = out["merchant"].map(lambda name: categorize_merchant(name, category_rules))
    return out
