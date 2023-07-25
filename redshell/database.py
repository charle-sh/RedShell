from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from redshell import config

Base = declarative_base()

database_path = config.read_config()['database_path']

engine = create_engine(f"sqlite:///{database_path}")

db_session = scoped_session(
    sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False
    )
)