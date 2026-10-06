import argparse
import logging
from pathlib import Path
from helen import store, pipeline

logger = logging.getLogger(__name__)


def cmd_add(args):
    con = store.connect(args.db)
    store.init_db(con)
    if args.checking:
        logger.info("checking: inserted %d new rows", pipeline.ingest_checking(con, args.checking))
    if args.visa:
        logger.info("visa: inserted %d new rows", pipeline.ingest_visa(con, args.visa))
    if not args.checking and not args.visa:
        logger.info("No checking or visa statements, taking no action; pass --checking and/or --visa")


def cmd_rebuild(args):
    args.db.unlink(missing_ok=True)
    con = store.connect(args.db)
    store.init_db(con)
    for csv in sorted(Path("data/raw").glob("*.csv")):
        logger.info("checking: %s; inserted %d new rows", csv, pipeline.ingest_checking(con, csv))
    for pdf in sorted(Path("data/raw").glob("*.pdf")):
        logger.info("visa: %s; inserted %d new rows", pdf, pipeline.ingest_visa(con, pdf))
        

def cmd_status(args):
    con = store.connect(args.db)
    store.init_db(con)
    df = store.read_transactions(con)
    logger.info("%d transactions", len(df))
    if not df.empty:
        print(df.groupby(["source"]).size())

def build_parser():
    p = argparse.ArgumentParser(prog="helen.ingest")
    p.add_argument("--db", type=Path, default=Path("data/helen.db"))
    p.add_argument("-v", "--verbose", action="store_true")

    sub = p.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="Ingest a checking CSV or a Visa PDF")
    add.add_argument("--checking", type=Path)
    add.add_argument("--visa", type=Path)
    add.set_defaults(func=cmd_add)

    sub.add_parser("rebuild", 
                   help="Delete the DB and re-run everything in data/raw").set_defaults(func=cmd_rebuild)
    sub.add_parser("status", help="Show counts by source").set_defaults(func=cmd_status)
    return p

def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    args.func(args)

if __name__ == "__main__":
    main()
    

