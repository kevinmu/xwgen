"""Class representing a crossword clue."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, List


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

    # returns True if the current entry shares any squares
    # with the passed-in Entry, false otherwise.
    def intersects_with(self, entry: 'Entry') -> bool:
        common_squares = set(self._get_square_indices()).\
            intersection(set(entry._get_square_indices()))
        if len(common_squares) == 0:
            print(f"{entry.index_str()} does not intersect with {self.index_str()}")
        return len(common_squares) > 0

    def _get_square_indices(self) -> List[Tuple[int, int]]:
        r = self.row_in_grid
        c = self.col_in_grid
        square_indices = []
        if self.direction == Direction.ACROSS:
            for i in range(self.answer_length):
                square_indices.append((r, c + i))
        else:
            for i in range(self.answer_length):
                square_indices.append((r + i, c))

        return square_indices

    def index_str(self) -> str:
        return f"{self.index}{self.direction.value}"

    def render_clue(self) -> None:
        print(f"{self.index_str()}: {self.clue} ({self.answer_length})")

    def __hash__(self) -> int:
        return hash(self.index_str())