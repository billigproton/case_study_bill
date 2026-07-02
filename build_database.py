"""Načte Excel sešit s žebříčky univerzit The Guardian do SQLite databáze."""

import re
import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
SOURCE_DATA_DIR = BASE_DIR / "source_data"
DB_PATH = BASE_DIR / "guardian_rankings.db"

# Mapování názvů listů v Excelu na názvy tabulek v SQLite
SHEET_TO_TABLE = {
    "The Guardian Ranking": "guardian_ranking",
    "The Guardian - Subject Areas": "guardian_subject_areas",
}


def normalize_column(name: str) -> str:
    """Převede název sloupce z Excelu (mezery, %, /) na bezpečný snake_case název pro SQLite."""
    name = name.strip().lower()
    name = name.replace("%", "pct").replace("/", "_per_")
    name = re.sub(r"[^0-9a-z]+", "_", name)
    return name.strip("_")


def find_source_workbook() -> Path:
    """Najde první .xlsx soubor ve složce source_data."""
    candidates = sorted(SOURCE_DATA_DIR.glob("*.xlsx"))
    if not candidates:
        raise FileNotFoundError(f"No .xlsx file found in {SOURCE_DATA_DIR}")
    return candidates[0]


def load_sheet(xls: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
    """Načte list z Excel sešitu do DataFrame a normalizuje názvy sloupců."""
    df = pd.read_excel(xls, sheet_name=sheet_name)
    df.columns = [normalize_column(col) for col in df.columns]
    return df


def write_table(conn: sqlite3.Connection, table_name: str, df: pd.DataFrame) -> None:
    """Zapíše DataFrame jako tabulku do SQLite a vytvoří indexy na institution/rok pro rychlejší dotazy."""
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    if "institution" in df.columns:
        conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_institution ON {table_name} (institution)')
    year_col = "ranking_year" if "ranking_year" in df.columns else "subject_area_year"
    if year_col in df.columns:
        conn.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_year ON {table_name} ({year_col})')


# ---------------------------------------------------------------------------
# TRANSFORMACE
# ---------------------------------------------------------------------------
# subject_area_rank_prev a subject_area_rank_change dostanou po zápisu přes pandas.to_sql
# typ REAL, protože sloupec kvůli chybějícím (NULL) hodnotám v Excelu skončí jako float64.
# Hodnoty jsou ale vždy celočíselné, proto sloupce po zápisu přetypujeme zpět na INTEGER.
RANK_COLUMNS_TO_FIX = {
    "guardian_subject_areas": ["subject_area_rank_prev", "subject_area_rank_change"],
}


def fix_rank_column_types(conn: sqlite3.Connection) -> None:
    """Přestaví tabulky z RANK_COLUMNS_TO_FIX tak, aby uvedené sloupce měly deklarovaný typ
    INTEGER místo REAL. SQLite neumí typ sloupce změnit přímo přes ALTER TABLE, proto se
    tabulka vytvoří znovu s opravenou definicí, data se do ní zkopírují přes CAST a na konci
    se obnoví i původní indexy, které zanikly společně s dropnutou tabulkou."""
    cur = conn.cursor()
    for table, columns in RANK_COLUMNS_TO_FIX.items():
        col_info = cur.execute(f"PRAGMA table_info({table})").fetchall()
        index_defs = cur.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
            (table,),
        ).fetchall()

        col_names = [row[1] for row in col_info]
        col_defs = [
            f'"{name}" {"INTEGER" if name in columns else col_type}'
            for _, name, col_type, *_ in col_info
        ]

        tmp_table = f"{table}__tmp"
        cur.execute(f'CREATE TABLE "{tmp_table}" ({", ".join(col_defs)})')

        select_cols = ", ".join(
            f'CAST("{name}" AS INTEGER)' if name in columns else f'"{name}"'
            for name in col_names
        )
        cur.execute(f'INSERT INTO "{tmp_table}" SELECT {select_cols} FROM "{table}"')

        cur.execute(f'DROP TABLE "{table}"')
        cur.execute(f'ALTER TABLE "{tmp_table}" RENAME TO "{table}"')

        for (index_sql,) in index_defs:
            cur.execute(index_sql)

        print(f"  Transformace: {table} -> {columns} přetypováno na INTEGER")


def main() -> None:
    """Najde zdrojový Excel sešit a všechny jeho listy podle SHEET_TO_TABLE uloží jako tabulky v SQLite."""
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
        fix_rank_column_types(conn)
        conn.commit()
    finally:
        conn.close()

    print(f"Database written to: {DB_PATH}")


if __name__ == "__main__":
    main()
