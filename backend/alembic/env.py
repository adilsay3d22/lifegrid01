import app.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.core.db import Base

target_metadata = Base.metadata


def run() -> None:
    if context.is_offline_mode():  # `alembic upgrade head --sql`: emit SQL for review
        context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    from app.core.db import engine

    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata, render_as_batch=conn.dialect.name == "sqlite",
                          compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run()
