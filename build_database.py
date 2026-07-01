"""Load the Guardian university ranking Excel workbook into a SQLite database."""

import re
import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DATA_DIR = BASE_DIR / "source_data"
DB_PATH = BASE_DIR / "guardian_rankings.db"

SHEET_TO_TABLE = {
    "The Guardian Ranking": "guardian_ranking",
    "The Guardian - Subject Areas": "guardian_subject_areas",
}


def normalize_column(name: str) -> str:
    name = name.strip().lower()
    name = name.replace("%", "pct").replace("/", "_per_")
    name = re.sub(r"[^0-9a-z]+", "_", name)
    return name.strip("_")


def find_source_workbook() -> Path:
    candidates = sorted(SOURCE_DATA_DIR.glob("*.xlsx"))
    if not candidates:
        raise FileNotFoundError(f"No .xlsx file found in {SOURCE_DATA_DIR}")
    return candidates[0]


def load_sheet(xls: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(xls, sheet_name=sheet_name)
    df.columns = [normalize_column(col) for col in df.columns]
    return df


def write_table(conn: sqlite3.Connection, table_name: str, df: pd.DataFrame) -> None:
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    if "institution" in df.columns:
        conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_institution ON {table_name} (institution)')
    year_col = "ranking_year" if "ranking_year" in df.columns else "subject_area_year"
    if year_col in df.columns:
        conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_year ON {table_name} ({year_col})')


def main() -> None:
    workbook_path = find_source_workbook()
    print(f"Reading workbook: {workbook_path.name}")
    xls = pd.ExcelFile(workbook_path)

    conn = sqlite3.connect(DB_PATH)
    try:
        for sheet_name, table_name in SHEET_TO_TABLE.items():
            if sheet_name not in xls.sheet_names:
                print(f"  Skipping missing sheet: {sheet_name}")
                continue
            df = load_sheet(xls, sheet_name)
            write_table(conn, table_name, df)
            print(f"  {sheet_name!r} -> table '{table_name}' ({len(df)} rows, {len(df.columns)} columns)")
        conn.commit()
    finally:
        conn.close()

    print(f"Database written to: {DB_PATH}")


if __name__ == "__main__":
    main()
