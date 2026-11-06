"""Connection settings, read from the environment so no credentials live in code."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def load_config(database: str | None = None) -> DbConfig:
    return DbConfig(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=database or os.getenv("MYSQL_DATABASE", "complaints_dw"),
    )
