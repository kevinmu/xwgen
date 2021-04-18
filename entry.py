"""Class representing a crossword clue."""
from enum import Enum
from typing import Optional


class Direction(Enum):
    ACROSS = 'A'
    DOWN = 'D'


class Entry:
    index: int
    direction: Direction
    clue: Optional[str]
    answer: Optional[str]

    def __init__(
        self,
        index: int,
        direction: Direction,
        clue: str = None,
        answer: str = None,
    ):
        self.index = index
        self.direction = direction
        self.clue = clue
        self.answer = answer

    def render_clue(self):
        print(f"{self.index}{self.direction.value}: {self.clue}")
