from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from cost_data.config import get_settings
from cost_data.models import Base


settings = get_settings()
engine: Engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@event.listens_for(engine, "connect")
def configure_sqlite(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


def init_db() -> None:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    alembic_config = Config(str(base_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(base_dir / "migrations"))
    command.upgrade(alembic_config, "head")
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS cost_item_fts USING fts5(
                    cost_item_id UNINDEXED,
                    code,
                    name,
                    description,
                    specification,
                    tokenize='trigram'
                )
                """
            )
        )


def rebuild_fts(session: Session, version_id: str | None = None) -> None:
    if version_id is None:
        session.execute(text("DELETE FROM cost_item_fts"))
        where_clause = ""
        params: dict[str, str] = {}
    else:
        session.execute(
            text(
                "DELETE FROM cost_item_fts WHERE cost_item_id IN "
                "(SELECT id FROM cost_items WHERE project_version_id=:version_id)"
            ),
            {"version_id": version_id},
        )
        where_clause = "WHERE project_version_id=:version_id"
        params = {"version_id": version_id}
    session.execute(
        text(
            "INSERT INTO cost_item_fts(cost_item_id, code, name, description, specification) "
            "SELECT id, coalesce(code,''), name, coalesce(description,''), "
            f"coalesce(specification,'') FROM cost_items {where_clause}"
        ),
        params,
    )


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
