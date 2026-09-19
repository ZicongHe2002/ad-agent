from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import CheckConstraint, MetaData, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app import models  # noqa: F401 -- registers every ORM table
from app.core.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))
# Alembic's check-constraint comparator deliberately omits type-bound Enum
# checks, but PostgreSQL/SQLite reflect them as ordinary checks. Present an
# explicit copy for comparison so real enum changes are still detected instead
# of either reporting every enum as deleted or ignoring enum checks entirely.
target_metadata = MetaData(naming_convention=Base.metadata.naming_convention)
for source_table in Base.metadata.tables.values():
    table = source_table.to_metadata(target_metadata)
    for constraint in list(table.constraints):
        if isinstance(constraint, CheckConstraint) and getattr(constraint, "_type_bound", False):
            table.constraints.remove(constraint)
            table.append_constraint(CheckConstraint(constraint.sqltext, name=constraint.name))


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
