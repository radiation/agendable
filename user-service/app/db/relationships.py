from common_lib.models import Base
from sqlalchemy import Column, ForeignKey, Table

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("user.id"), primary_key=True),
    Column("role_id", ForeignKey("role.id"), primary_key=True),
)

group_users = Table(
    "group_users",
    Base.metadata,
    Column("user_id", ForeignKey("user.id"), primary_key=True),
    Column("group_id", ForeignKey("group.id"), primary_key=True),
)
