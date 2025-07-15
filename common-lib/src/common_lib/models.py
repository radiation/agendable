from typing import Any, Union
from uuid import UUID

from sqlalchemy import Integer, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    __abstract__ = True
    id: Mapped[Union[int, UUID]] = mapped_column(Integer, primary_key=True)

    def as_dict(self) -> dict[str, Any]:
        return {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}
