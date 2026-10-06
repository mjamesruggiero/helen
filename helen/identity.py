from hashlib import sha1
import pandas as pd

def checking_txn_id(date, amount, description, occurrence: int) -> str:
    key = f"{date}|{amount}|{description}|{occurrence}"
    return sha1(key.encode("utf-8")).hexdigest()


def visa_txn_id(txn_id: str):
    return txn_id.strip()


def assign_txn_ids(transactions: pd.DataFrame, source: str) -> pd.DataFrame:
    df = transactions.copy()    
    # look for repeats within the given dataframe
    if "checking" == source:
        occurrences = df.groupby(["date", "amount", "merchant_raw"]).cumcount()
        df["txn_id"] = [
            checking_txn_id(d, a, m, o) 
            for d, a, m, o in zip(df["date"], df["amount"], df["merchant_raw"], occurrences)
        ]
    if "visa" == source:
        df["txn_id"] = df["reference"].map(visa_txn_id)

    return df
