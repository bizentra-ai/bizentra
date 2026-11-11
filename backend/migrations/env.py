from alembic import context
from app.database import Base, engine
from app import models
from app import domain_models
from app import control_models

with engine.connect() as connection:
    if engine.dialect.name=='sqlite':
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
        connection.commit()
    context.configure(connection=connection,target_metadata=Base.metadata,render_as_batch=engine.dialect.name=='sqlite')
    with context.begin_transaction():
        context.run_migrations()
    if engine.dialect.name=='sqlite':
        if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():raise RuntimeError('Migration produced invalid foreign keys')
        connection.commit()
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
