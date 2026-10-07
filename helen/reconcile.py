import re
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Totals:
    previous_balance: float
    payments: float
    other_credits: float
    purchases: float
    fees: float
    interest: float
    new_balance: float


@dataclass(frozen=True)
class Discrepancy:
    check: str # credits or charges or balance_identity
    expected: float
    actual: float
    delta: float # actual - expected (naturally)


def parse_control_totals(pages: list[str]) -> Totals:
    """Regex the printed $ totals out of the statement text.
    Pure function"""
    PATTERNS = {
        "previous_balance": r"Previous Balance",
        "payments": r"TOTAL PAYMENTS FOR THIS PERIOD",
        "other_credits": r"TOTAL OTHER CREDITS FOR THIS PERIOD",
        "purchases": r"TOTAL PURCHASES, BALANCE TRANSFERS & OTHER CHARGES FOR THIS PERIOD",
        "fees": r"TOTAL FEES CHARGED FOR THIS PERIOD",
        "interest": r"TOTAL INTEREST CHARGED FOR THIS PERIOD",
        "new_balance": r"New Balance" 
    }
    AMOUNT = r"\s+\$?([\d,]+\.\d{2})"
    found = {}

    text = "\n".join(pages)
    for field, label in PATTERNS.items():
        m = re.search(label + AMOUNT, text)
        if m:
            found[field] = float(m.group(1).replace(",", ""))
        else:
            logger.warning("control total not found %s", field)
            found[field] = 0.0

    return Totals(**found)


def _check(name, expected, actual, tolerance):
    delta = actual - expected
    if abs(delta) > tolerance:
        return Discrepancy(check=name, expected=expected, actual=actual, delta=delta)
    return None


def reconcile(df, totals: Totals, tol: float=0.01) -> list[Discrepancy]:
    """Return a list of checks that failed (i.e. empty list means 'clean')
    - credits: df[df.amount > 0].amount.sum() vs totals.other_credits
    - charges: df[df.amount < 0].amount.sum() vs totals.purchases
    - balance_identity: prev - payments - credits + purchased + fees + int vs new_balance
    """
    credits = df[df["amount"] > 0]["amount"].sum()
    charges = -df[df["amount"] < 0]["amount"].sum()
    identity = (totals.previous_balance - totals.payments - totals.other_credits 
        + totals.purchases + totals.fees + totals.interest)
    checks = [
        _check("credits", totals.other_credits, credits, tol),
        _check("charges", totals.purchases, charges, tol),
        _check("balance_identity", totals.new_balance, identity, tol),
    ]
    return [c for c in checks if c is not None]
