"""Class representing a crossword clue."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Direction(Enum):
    ACROSS = 'A'
    DOWN = 'D'


@dataclass
class Entry:
    index: int
    direction: Direction
    row_in_grid: int
    col_in_grid: int
    answer_length: int
    clue: Optional[str] = None
    answer: Optional[str] = None

    def index_str(self) -> str:
        return f"{self.index}{self.direction.value}"

    def render_clue(self) -> None:
        print(f"{self.index_str()}: {self.clue} ({self.answer_length})")

    def __hash__(self) -> int:
        return hash(self.index_str())