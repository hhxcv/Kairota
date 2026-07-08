from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_baseline_migration_upgrades_and_downgrades(tmp_path: Path) -> None:
    db_path = tmp_path / "kairota.sqlite"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    command.upgrade(config, "head")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    assert "alembic_version" in inspect(engine).get_table_names()

    command.downgrade(config, "base")
    with engine.connect() as connection:
        row_count = connection.execute(text("select count(*) from alembic_version"))
        assert row_count.scalar_one() == 0
