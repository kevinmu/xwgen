"""Class representing a crossword clue."""
from enum import Enum


class Direction(Enum):
    ACROSS = 'A'
    DOWN = 'D'


class Entry:
    answer: str
    clue: str
    index: int
    direction: Direction

    def __init__(self, answer: str, clue: str, index: int, direction: Direction):
        self.answer = answer
        self.clue = clue
        self.index = index
        self.direction = direction

    def render_clue(self):
        print(f"{self.index}{self.direction}: {self.clue}\n")
