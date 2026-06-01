"""Generic async CRUD repository base class."""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepo(Generic[ModelT]):
    """Generic async CRUD repository.

    Domain repositories extend this class and set ``model`` to their
    SQLAlchemy model class.  The session is injected via the constructor
    (provided by FastAPI ``Depends``).

    Important: this layer never calls ``session.commit()``— the service
    layer owns transaction boundaries per §9.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, filters: dict[str, Any] | None = None) -> list[ModelT]:
        """Return a list of rows, optionally filtered by column equality."""
        stmt = select(self.model)
        if filters:
            for col, value in filters.items():
                stmt = stmt.where(getattr(self.model, col) == value)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, pk: int) -> ModelT | None:
        """Return a single row by primary key, or ``None``."""
        return await self.session.get(self.model, pk)

    async def create(self, obj: ModelT) -> ModelT:
        """Add a new object and flush to materialise its PK."""
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: ModelT, data: dict[str, Any]) -> ModelT:
        """Apply a dict of updates to an existing object and flush."""
        for key, value in data.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        """Mark an object for deletion and flush."""
        await self.session.delete(obj)
        await self.session.flush()
