"""Pure cleaning/parsing functions. No I/O"""
import re
from datetime import date
import pandas as pd

def parse_amount(raw: str | float) -> float:
    """ '-1,234.56' or '-7.99' -> float. Empty -> raises."""
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = str(raw).replace(",", "").replace('"', "").strip()
    return float(cleaned)


def parse_date(raw: str) -> date:
    """'08/07/2026' -> datetime.date"""
    return pd.to_datetime(raw, format="%m/%d/%Y").date()


def extract_txn_type(desc: str) -> str:
    """Normalize the leading transaction-type labels.

    Format A card rows start with PURCHASE / RECURRING PAYMENT / PURCHASE RETURN / 
    ATM WITHDRWAWAL / MONEY TRANSFER. Format B rows start with an originator, 
    then a type (TRANSFER, PAYROLL, INVESTMENT, AUTO PAY) """
    d = desc.upper()
    known_prefixes = (
        "RECURRING PAYMENT", "PURCHASE RETURN", "PURCHASE",
        "ATM WITHDRAWAL", "ATM CHECK DEPOSIT", "MONEY TRANSFER",
        "ONLINE TRANSFER", "CHECK",
    )
    for p in known_prefixes:
        if d.startswith(p):
                return p
    # format B, where we classify by keywords
    keywords = ("PAYROLL", "TRANSFER", "INVESTMENT", "AUTO PAY",
               "BILLPAY", "UTILITY", "INS_PAYMT", "SWEEP", "EPAY")
    for kw in keywords:
        if kw in d:
            return kw

    return "OTHER"


_AUTH_RE = re.compile(r"AUTHORIZED ON\s+\d{2}/\d{2}\s+(?P<rest>.*)")
_CARD_RE = re.compile(r"\s+CARD\s+\d+\s*$")
_REF_RE = re.compile(r"\s+[SP]\d{10,}.*$")          # S3862... / P0000... reference tails
_STATE_TAIL_RE = re.compile(r"\s+[A-Z]{2}\s*$")     # trailing " CA", " WA", " NY"
_TXN_PREFIXES = (
    "RECURRING PAYMENT", "PURCHASE RETURN", "PURCHASE",
    "ATM WITHDRAWAL", "MONEY TRANSFER",
)


def extract_merchant(desc: str) -> str:
    """Pull a sort-of-clean merchant name out of messy descriptions.

    Format A (has 'AUTHORIZED ON'): strip type + auth clause + card/ref/location
    Format B (no 'AUTHORIZED ON'): first ~16 chars are originator/merchant
    """
    text = " ".join(desc.split())  # collapse extra whitespace
    m = _AUTH_RE.search(text)
    if m: # ----------- FORMAT A --------------------
        rest = m.group("rest")
        rest = _CARD_RE.sub("", rest)
        rest = _REF_RE.sub("", rest)
        rest = _STATE_TAIL_RE.sub("", rest)
        # what's left is 'MERCHANT ... location'; keep leading tokens
        return rest.strip().upper()

    # ----------- FORMAT B --------------- first field is fixed-width originator
    head = desc[:16].strip()
    return " ".join(head.split()).upper()


def clean(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Raw rows -> tidy typed frame. Pure, no I/O"""
    out = pd.DataFrame()
    out["date"] = df_raw["DATE"].map(parse_date)
    out["date"] = pd.to_datetime(out["date"])
    out["month"] = out["date"].dt.to_period("M")
    out["amount"] = df_raw["AMOUNT"].map(parse_amount)
    out["is_outflow"] = out["amount"] < 0
    out["txn_type"] = df_raw["DESCRIPTION"].map(extract_txn_type)
    out["merchant_raw"] = df_raw["DESCRIPTION"].astype(str)
    out["merchant"] = df_raw["DESCRIPTION"].map(extract_merchant)
    out["check_no"] = df_raw["CHECK #"].fillna("").astype(str).str.strip()
    return out.reset_index(drop=True)
