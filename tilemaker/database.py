"""
Actual database business logic.
"""

from sqlmodel import Session, SQLModel, create_engine

from .settings import settings

engine = create_engine(settings.database_url)


def create_database_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    return Session(engine)
