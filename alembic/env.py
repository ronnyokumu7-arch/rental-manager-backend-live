import os
import sys
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool, engine_from_config
from sqlalchemy.dialects import postgresql
from app.db.database import Base, engine
from app.models import (
    bookings, clients, contracts, invoices, password_reset,
    payments, subscriptions, tenant_policies, tenant_profile,
    tenants, users, vehicles, activity_log,
)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

def skip_json_server_default(context, inspected_column, metadata_column, inspected_default, metadata_default, rendered_metadata_default):
    if isinstance(inspected_column.type, (postgresql.JSON, postgresql.JSONB)) or \
       isinstance(metadata_column.type, (postgresql.JSON, postgresql.JSONB)):
        return False
    return None

def run_migrations_offline() -> None:
    url = str(engine.url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=skip_json_server_default,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=skip_json_server_default,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
