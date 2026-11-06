"""Thin helpers around PyMySQL."""
from pathlib import Path

import pymysql

from warehouse.config import DbConfig

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def connect(cfg: DbConfig):
    """Connect, creating the database first if it does not exist."""
    bootstrap = pymysql.connect(
        host=cfg.host, port=cfg.port, user=cfg.user, password=cfg.password, autocommit=True
    )
    with bootstrap.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{cfg.database}` CHARACTER SET utf8mb4"
        )
    bootstrap.close()
    return pymysql.connect(
        host=cfg.host,
        port=cfg.port,
        user=cfg.user,
        password=cfg.password,
        database=cfg.database,
        autocommit=False,
        charset="utf8mb4",
    )


def run_script(conn, filename: str) -> None:
    """Run a .sql file statement by statement. Files must not use ';' inside strings."""
    text = (SQL_DIR / filename).read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if not line.strip().startswith("--")]
    with conn.cursor() as cur:
        for statement in "\n".join(lines).split(";"):
            if statement.strip():
                cur.execute(statement)
