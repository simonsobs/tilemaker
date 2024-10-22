"""
Shows how the cascade option does not work with SQLModel
"""

import sys

mode = sys.argv[1]

if mode == "model":
    from sqlmodel import Field, Relationship, Session, SQLModel, create_engine

    class Parent(SQLModel, table=True):
        id: int = Field(primary_key=True)

        children: list["Child"] = Relationship(
            back_populates="parent",
            sa_relationship_kwargs={"cascade": "all, delete-orphan"},
        )

    class Child(SQLModel, table=True):
        id: int = Field(primary_key=True)
        parent_id: int = Field(foreign_key="parent.id")
        parent: Parent = Relationship(back_populates="children")

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        parent = Parent()
        children = [Child(parent=parent) for _ in range(3)]

        session.add_all([parent] + children)
        session.commit()

    with Session(engine) as session:
        parent = session.query(Parent).delete()

        # session.delete(parent)
        session.commit()

    with Session(engine) as session:
        assert session.query(Child).count() == 0

elif mode == "alchemy":
    from sqlalchemy import Column, ForeignKey, Integer, create_engine
    from sqlalchemy.orm import Session, declarative_base, relationship

    Base = declarative_base()

    class Parent(Base):
        __tablename__ = "parent"
        id: int = Column(Integer, primary_key=True)
        children = relationship("Child", cascade="all, delete-orphan")

    class Child(Base):
        __tablename__ = "child"
        id: int = Column(Integer, primary_key=True)
        parent_id: int = Column(ForeignKey("parent.id"))
        parent = relationship("Parent", back_populates="children")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        parent = Parent()
        children = [Child(parent=parent) for _ in range(3)]

        session.add_all([parent] + children)
        session.commit()

    with Session(engine) as session:
        parent = session.query(Parent).delete()

        # session.delete(parent)
        session.commit()

    with Session(engine) as session:
        assert session.query(Child).count() == 0

else:
    pass
