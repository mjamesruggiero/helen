import sqlite3, logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)
DEFAULT_DB = Path("data/helen.db")

COLUMNS = [ 
    "txn_id", "date", "amount", "merchant",
    "merchant_raw", "is_outflow", "txn_type",
    "check_no", "source", "source_file",
]

def convert_to_rows(df: pd.DataFrame):
    """Need to normalize Pandas values to values that SQLite won't hate
    and sort deterministically"""
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d") 
    out["is_outflow"] = out["is_outflow"].astype(int)
    out["amount"] =  out["amount"].astype(float)
    out = out[COLUMNS]
    return list(out.itertuples(index=False, name=None))


def connect(db_path=DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    return conn


def init_db(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS transactions (
               txn_id       TEXT PRIMARY KEY,
               date         TEXT NOT NULL,          -- ISO 'YYYY-MM-DD'
               amount       REAL NOT NULL,          -- signed; outflow negative
               merchant     TEXT,
               merchant_raw TEXT,
               is_outflow   INTEGER NOT NULL,        -- 0/1 (SQLite has no bool)
               txn_type     TEXT,
               check_no     TEXT,
               source       TEXT NOT NULL,           -- 'checking' | 'visa'
               source_file  TEXT,
               ingested_at  TEXT DEFAULT (datetime('now'))
           );"""
    )
    con.commit()

def upsert_transactions(con: sqlite3.Connection, df: pd.DataFrame) -> int:
    """INSERT OR IGNORE each row keyed on txn_id.
    Returns rows actually inserted. 
    Idempotent: re-running the same month inserts zero records"""
    rows = convert_to_rows(df)
    placeholder_string = ", ".join(["?"] * len(COLUMNS))
    sql = f"INSERT OR IGNORE INTO transactions({', '.join(COLUMNS)}) VALUES ({placeholder_string})"
    before = con.total_changes
    con.executemany(sql, rows)
    con.commit()
    after = con.total_changes - before
    return after
    

def read_transactions(con) -> pd.DataFrame:
    query = "SELECT * FROM transactions;"
    return pd.read_sql_query(query, con)
