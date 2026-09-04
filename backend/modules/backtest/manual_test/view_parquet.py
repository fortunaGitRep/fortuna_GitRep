"""
Quick viewer for upstox_universe_INE04I401011.parquet

Setup (one time):
    pip install pandas pyarrow

Usage:
    python view_parquet.py
    python view_parquet.py --file path/to/other.parquet
    python view_parquet.py --csv out.csv --xlsx out.xlsx
"""

import argparse
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="View / export a parquet file")
    parser.add_argument(
        "--file",
        default="upstox_universe_INE04I401011.parquet",
        help="Path to the parquet file (default: %(default)s)",
    )
    parser.add_argument("--csv", help="Optional path to also export as CSV")
    parser.add_argument("--xlsx", help="Optional path to also export as Excel")
    parser.add_argument(
        "--rows", type=int, default=20, help="Number of rows to preview (default: 20)"
    )
    args = parser.parse_args()

    df = pd.read_parquet(args.file)

    print(f"File: {args.file}")
    print(f"Shape: {df.shape[0]} rows x {df.shape[1]} columns\n")

    print("Dtypes:")
    print(df.dtypes, "\n")

    print(f"First {args.rows} rows:")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(df.head(args.rows))

    print(f"\nLast {args.rows} rows:")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(df.tail(args.rows))

    print("\nSummary stats:")
    print(df.describe(include="all"))

    if args.csv:
        df.to_csv(args.csv, index=False)
        print(f"\nSaved CSV -> {args.csv}")

    if args.xlsx:
        df_export = df.copy()
        # Excel can't handle tz-aware datetimes; strip tz if present
        for col in df_export.select_dtypes(include=["datetimetz"]).columns:
            df_export[col] = df_export[col].dt.tz_localize(None)
        df_export.to_excel(args.xlsx, index=False)
        print(f"Saved Excel -> {args.xlsx}")


if __name__ == "__main__":
    main()
