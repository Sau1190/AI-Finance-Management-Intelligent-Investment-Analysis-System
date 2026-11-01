"""Command line for the Phase 13 experiments (offline, no network, no database).

  python -m ml_experiments.run volatility --source matplotlib-goog
  python -m ml_experiments.run volatility --prices my_prices.csv [--price-column adj_close]
  python -m ml_experiments.run sentiment  --data my_labelled_headlines.csv

Run from the `backend/` folder. Reports are written as JSON to --out
(default storage/ml_reports/) and never overwrite an earlier report.
Exit code 0 even for `insufficient_data` (that is a valid, honest outcome).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

from ml_experiments import EXPERIMENTAL_NOTICE
from ml_experiments.common import file_sha256, write_report


def _df_fingerprint(df) -> str:
    return hashlib.sha256(df.to_csv(index=False).encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ml_experiments.run", description=EXPERIMENTAL_NOTICE)
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("volatility", help="forecast next-21-day volatility vs naive baselines")
    g = v.add_mutually_exclusive_group(required=True)
    g.add_argument("--prices", help="CSV with date and price columns")
    g.add_argument("--source", choices=["matplotlib-goog"], help="built-in demonstration data")
    v.add_argument("--price-column", default="close")
    s = sub.add_parser("sentiment", help="compare a TF-IDF classifier with the Phase 8 lexicon")
    s.add_argument("--data", required=True, help="labelled CSV: text,label[,group]")
    for p in (v, s):
        p.add_argument("--out", default="storage/ml_reports")
    args = parser.parse_args(argv)

    print(EXPERIMENTAL_NOTICE, file=sys.stderr)

    if args.cmd == "volatility":
        from ml_experiments import volatility_experiment as exp

        if args.source:
            df, info = exp.load_matplotlib_goog()
            source = {"name": info["dataset"], "sha256_of_cleaned_rows": _df_fingerprint(df)}
        else:
            df, info = exp.load_prices(args.prices, args.price_column)
            source = {"name": args.prices, "sha256": file_sha256(args.prices), "price_column": args.price_column}
        report = exp.run(df, info, source)
    else:
        from ml_experiments import sentiment_experiment as exp

        df, info = exp.load_labelled(args.data)
        report = exp.run(df, info, {"name": args.data, "sha256": file_sha256(args.data)})

    path = write_report(report, args.out)
    print(json.dumps({"status": report["status"], "report": str(path), "message": report.get("message")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
