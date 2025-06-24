from typing import Union
from uuid import UUID

from sqlalchemy import Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    __abstract__ = True
    id: Mapped[Union[int, UUID]] = mapped_column(Integer, primary_key=True)
