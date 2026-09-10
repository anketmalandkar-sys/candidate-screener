from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Imported for the side effect: `app.models` pulls in every feature's model
# module, registering all mappers on Base.metadata.
from app import models  # noqa: F401
from app.models.base import Base
from app.utilities.config import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The URL comes from the environment, never from alembic.ini, so there is no
# connection string committed to the repo.
config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
