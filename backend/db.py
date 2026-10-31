"""SQLite helpers. One file database: backend/data.db"""
import os
import sqlite3

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def read(table: str, where: str = "", params: tuple = ()) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(f"SELECT * FROM {table} {where}", conn, params=params)


def write(tables: dict[str, pd.DataFrame]) -> None:
    """Replace each table with the given DataFrame."""
    with connect() as conn:
        for name, df in tables.items():
            df.to_sql(name, conn, if_exists="replace", index=False)
