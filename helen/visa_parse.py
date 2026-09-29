import re
from datetime import date, datetime
import pandas as pd


def classify_section(line: str, current: str | None) -> str | None:
    if "Other Credits" in line:
        return "credits"
    if "Purchases, Balance Transfers" in line:
        return "charges"
    if "Interest Charged" in line:
        return "interest"

    return current

def parse_line(line: str, section: str | None) -> dict | None:
    if section == "interest" or section is None:
        return None

    if section == "charges":
        is_outflow = True
    else:
        is_outflow = False
    
    ROW = re.compile(
        r"^(?P<card_ending>\d{4})\s+(?P<trans>\d{2}/\d{2})\s+(?P<post>\d{2}/\d{2})\s+"
        r"(?P<reference>\S+)\s+(?P<merchant_raw>.*?)\s+(?P<amount>[\d,]+\.\d{2})$"
    )
    match = ROW.match(line)
    if match:
        result = match.groupdict()

        result["amount"] = parse_amount(result["amount"])
        result["merchant"] = extract_visa_merchant(result["merchant_raw"])
        result["is_outflow"] = is_outflow
        if is_outflow:
            result["amount"] = result["amount"] * -1
    else:
        result = None
    return result


def parse_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_visa_merchant(desc: str) -> str:
    merchant = "UNKNOWN"
    if desc.startswith("PAYPAL *"):
        desc = desc.replace("PAYPAL *", "", 1)
        pieces = desc.split(" ")
        merchant = " ".join(pieces[0:2])
    if desc.startswith("CASH BACK REDEMPTION"):
        merchant = "CASH BACK REDEMPTION"
    else:
        pieces = desc.split(" ")
        merchant = " ".join(pieces[0:2])
    return merchant


def infer_year(trans_mmdd: str, period_start: date, period_end: date) -> int:
    month_num = int(trans_mmdd.split("/")[0]) # "12/25" becomes 12
    if period_start.year == period_end.year:
        return period_start.year 
    if month_num >= period_start.month:
        return period_start.year
    else:
        return period_end.year
    


def parse_statement(pages: list[str]) -> pd.DataFrame:
    # grab the dates
    match = re.search(r"(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})", pages[0])
    if match:
        start_date, end_date = (
            datetime.strptime(d, "%m/%d/%Y").date() for d in match.groups()
        )
    else:
        raise ValueError(f"No statement period found in {pages[0]!r}")

    # walk the page
    rows = []
    section = None
    for page in pages:
        for line in page.splitlines():
            section = classify_section(line, section)
            row = parse_line(line, section)
            if row is not None:
                rows.append(row)
    df = pd.DataFrame(rows)

    years = df["trans"].map(lambda t: infer_year(t, start_date, end_date))
    #You still owe: date, month, txn_type, check_no, source
    df["date"] = pd.to_datetime(years.astype(str) + "/" + df["trans"], format="%Y/%m/%d")
    df["month"] = df["date"].dt.to_period("M")
    df["txn_type"] = df["is_outflow"].map({True: "PURCHASE", False: "CREDIT"})
    df["check_no"] = ""
    df["source"] = "visa"

    return df
