from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class Optional(Generic[T]):
    _content: T | None

    def unwrap(self) -> T:
        return self.excepts("Unwrapping the null value")

    def excepts(self, msg: str) -> T:
        if self._content is None:
            raise Exception(msg)
        return self._content

    def unwrap_or(self, variant: T) -> T:
        return variant if self._content is None else self._content

    def is_none(self) -> bool:
        return self._content is None

    def is_some(self) -> bool:
        return self._content is not None
