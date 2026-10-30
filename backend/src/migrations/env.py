from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from config import DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER
from database.database import Base
import models  # noqa: F401  # Импорт обеспечивает регистрацию всех моделей в Base.metadata

config = context.config
section = config.config_ini_section
config.set_section_option(section, "DB_HOST", DB_HOST)
config.set_section_option(section, "DB_USER", DB_USER)
config.set_section_option(section, "DB_PASS", DB_PASS)
config.set_section_option(section, "DB_NAME", DB_NAME)
config.set_section_option(section, "DB_PORT", DB_PORT)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Запуск миграций в offline-режиме."""
    url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Запуск миграций в online-режиме."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = (
        f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
