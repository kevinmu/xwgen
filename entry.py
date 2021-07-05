"""Class representing a crossword clue."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, List, Dict

from word_filler import WordFiller
from square import Square


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
    squares: List[Square] = None
    cached_num_matches: Dict[str, int] = field(default_factory=dict)

    # returns True if the current entry shares any squares
    # with the passed-in Entry, false otherwise.
    def intersects_with(self, entry: 'Entry') -> bool:
        common_squares = set(self._get_square_indices()).\
            intersection(set(entry._get_square_indices()))
        if len(common_squares) == 0:
            print(f"{entry.index_str()} does not intersect with {self.index_str()}")
        return len(common_squares) > 0

    def get_current_hint(self) -> str:
        current_hint = ""
        for sq in self.squares:
            current_hint += sq.letter if sq.letter is not None else "."
        return current_hint

    def is_complete(self) -> bool:
        for sq in self.squares:
            if sq.letter is None:
                return False
        return True

    def get_possible_matches(self, word_filler: WordFiller) -> List[str]:
        current_hint = self.get_current_hint()
        return word_filler.get_possible_words_for_hint(current_hint)

    def get_num_possible_matches(self, word_filler: WordFiller):
        current_hint = self.get_current_hint()
        if current_hint not in self.cached_num_matches:
            self.cached_num_matches[current_hint] = len(self.get_possible_matches(word_filler))

        return self.cached_num_matches[current_hint]

    # Uses a heuristic to determine the priority of the given entry during
    # puzzle filling.
    def get_fill_priority(self, word_filler: WordFiller) -> int:
        # no need to fill if the entry is already filled
        if self.is_complete():
            return 0

        num_possible_matches = self.get_num_possible_matches(word_filler)

        # no need to fill if the entry cannot be filled
        if num_possible_matches == 0:
            return 0

        return max(0, 300 - num_possible_matches*10) + self.answer_length

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