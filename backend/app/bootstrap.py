from __future__ import annotations

from pathlib import Path

import pymysql
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.compilers.style_kits import StyleKitRegistry
from app.config import ROOT_DIR, get_settings
from app.models import AssetCatalogRecord, StyleKitRecord


BACKEND_DIR = Path(__file__).resolve().parents[1]


def ensure_database_exists() -> None:
    settings = get_settings()
    if settings.database_url_override:
        return
    connection = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        database_name = settings.mysql_database
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()


def run_migrations() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


def seed_catalogs() -> None:
    settings = get_settings()
    engine = create_engine(settings.sync_database_url)
    registry = StyleKitRegistry()
    try:
        with Session(engine) as session:
            for item in registry.list_public():
                session.merge(
                    StyleKitRecord(
                        id=item["id"],
                        name=item["name"],
                        version="1.0.0",
                        config_json=item,
                        active=1,
                    )
                )
            for item in registry.assets():
                session.merge(
                    AssetCatalogRecord(
                        id=item["id"],
                        category=item["category"],
                        metadata_json=item,
                        active=1,
                    )
                )
            session.commit()
    finally:
        engine.dispose()


def bootstrap_database() -> None:
    ensure_database_exists()
    run_migrations()


if __name__ == "__main__":
    bootstrap_database()
    seed_catalogs()
    print(f"Database is ready for {ROOT_DIR.name}.")
