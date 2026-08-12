"""Pure analysis functions: monthly outgo, income vs. outgo, recurring detection"""
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def monthly_outgo(df, exclude_categories=("Transfers", "Income")):
    """Total spend per month, excluding transfers & income"""
    spend = df[df["is_outflow"] & ~df["category"].isin(exclude_categories)]
    outgo = spend.groupby("month")["amount"].sum().abs()
    return outgo.sort_index()


def monthly_by_category(df, exclude_categories=("Transfers", "Income")):
    spend = df[df["is_outflow"] & ~df["category"].isin(exclude_categories)].copy()
    spend["spend"] = -spend["amount"] # convert to positive
    pivot = (spend.pivot_table(
        index="month",
        columns="category",
        values="spend",
        aggfunc="sum",
        fill_value=0
    ).sort_index())
    return pivot


def income_vs_outgo(df) -> pd.DataFrame:
    """Per-month income, outgo, and net. Paychecks only count as income."""
    income = (
        df[(df["category"] == "Income") & (df["amount"] > 0)]
        .groupby("month")["amount"]
        .sum()
    )
    outgo = monthly_outgo(df)  # already a month-indexed Series of positive spend

    out = pd.DataFrame({"income": income, "outgo": outgo}).fillna(0)
    out["net"] = out["income"] - out["outgo"]
    logger.debug("income_vs_outgo:\n%s", out)
    return out.sort_index()


def average_monthly_outgo(df, 
                          exclude_first=True, 
                          exclude_last=True, 
                          exclude_categories=("Transfers", "Income")) -> float:
    s = monthly_outgo(df, exclude_categories)
    if exclude_first:
        s = s.drop(s.index[0])
    if exclude_last:
        s = s.drop(s.index[-1])
    return float(s.mean())



def detect_recurring(df, 
                     min_months=3, 
                     max_cv=0.15, 
                     exclude_categories=("Transfers", "Income")) -> pd.DataFrame:
    spend = df[df["is_outflow"] & ~df["category"].isin(exclude_categories)].copy()
    spend["spend"] = -spend["amount"]
    monthly = spend.groupby(["merchant", "month"])["amount"].sum().abs()
    g = monthly.groupby(level="merchant")
    stats = pd.DataFrame({ 
        "months_seen": g.size(),
        "monthly_amount": g.mean(),
        "std": g.std() 
    })
    stats["std"] = stats["std"].fillna(0)
    stats["cv"] = stats["std"] / stats["monthly_amount"]
    
    # apply the thresholds
    keep = (stats["months_seen"] >= min_months) & (stats["cv"] <= max_cv)
    recurring = stats[keep]

    # now re-decorate with merchant category and realize yearly cost
    categories = spend.groupby("merchant")["category"].first()
    out = recurring.copy()
    out["merchant"] = out.index
    out["category"] = out["merchant"].map(categories)
    out["annualized"] = out["monthly_amount"] * 12

    # slim it down and sort by annualized
    out = out[["merchant", "category", "months_seen", "monthly_amount", "annualized"]]
    out = out.sort_values("annualized", ascending=False).reset_index(drop=True)
    return out

    
