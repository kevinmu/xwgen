"""Class representing the crossword grid."""
from typing import List, Tuple, Dict

from entry import Entry, Direction
from square import Square
from string_utils import merge_strings_with_same_num_lines
from string_utils import remove_last_line_from_string


class Puzzle:
    rows: int
    cols: int
    grid: List[List[Square]]
    index: int
    entries: Dict[str, Entry]

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols

        self.grid = [[Square() for j in range(cols)] for i in range(rows)]
        '''self.mark_black_squares([
            (0, 8),
            (1, 8),
            (2, 8),
            (3, 0), (3, 1), (3, 2), (3, 11),
            (4, 5), (4, 10),
            (5, 4), (5, 9), (5, 13), (5, 14),
            (6, 3), (6, 14),
            (7, 7),
        ])'''

        self.mark_black_squares([
            (0, 4), (0,9),
            (1, 4), (1, 9),
            (2, 4),
            (3, 6), (3, 12), (3, 13), (3, 14),
            (4, 11),
            (5, 0), (5, 1), (5, 2), (5, 3), (5, 7), (5, 8),
            (6, 0),
            (7, 4), (7, 5), (7, 9), (7, 10)
        ])
        self.index = 0

        self.number_squares()
        self.entries = self.generate_entries_from_numbered_squares()

    def get_next_index(self):
        self.index += 1
        return self.index

    # Crossword boards have rotational symmetry, so if (r, c) is specified,
    # then both (r, c) and (rows-1-r, cols-1-c) are marked.
    def mark_black_squares(self, coordinates: List[Tuple[int, int]]):
        for coordinate in coordinates:
            r = coordinate[0]
            c = coordinate[1]
            self.grid[r][c].is_black = True
            self.grid[self.rows - 1 - r][self.cols - 1 - c].is_black = True

    def number_squares(self) -> None:
        for r, row in enumerate(self.grid):
            for c, square in enumerate(row):
                if square.is_black:
                    continue
                    
                has_empty_square_above = (r == 0 or self.grid[r - 1][c].is_black)
                has_empty_square_on_left = (c == 0 or self.grid[r][c - 1].is_black)
                # this represents the start of a new word; give it an index
                if has_empty_square_above or has_empty_square_on_left:
                    square.index = self.get_next_index()

                # specify what kinds of words this square will start
                square.starts_down_word = has_empty_square_above
                square.starts_across_word = has_empty_square_on_left

    def generate_entries_from_numbered_squares(self) -> Dict[str, Entry]:
        entries = {}
        for r, row in enumerate(self.grid):
            for c, square in enumerate(row):
                if square.starts_across_word:
                    i = 0
                    while c + i < self.cols and not self.grid[r][c+i].is_black:
                        i += 1

                    entry = Entry(square.index, Direction.ACROSS, r, c, i)
                    entries[entry.index_str()] = entry
                if square.starts_down_word:
                    i = 0
                    while r + i < self.rows and not self.grid[r+i][c].is_black:
                        i += 1

                    entry = Entry(square.index, Direction.DOWN, r, c, i)
                    entries[entry.index_str()] = entry

        return entries

    def fill_entry(self, entry: Entry, answer: str) -> None:
        assert len(answer) == entry.answer_length, \
            f"Answer {answer} has length {len(answer)}, but entry " \
            f"{entry.index_str()} has length {entry.answer_length}"
        r = entry.row_in_grid
        c = entry.col_in_grid
        if entry.direction == Direction.DOWN:
            for i, letter in enumerate(answer):
                self.grid[r + i][c].letter = letter
        else:
            for i, letter in enumerate(answer):
                self.grid[r][c+i].letter = letter

    def erase_entry(self, entry: Entry) -> None:
        r = entry.row_in_grid
        c = entry.col_in_grid
        if entry.direction == Direction.DOWN:
            for i in range(entry.answer_length):
                self.grid[r + i][c].letter = None
        else:
            for i in range(entry.answer_length):
                self.grid[r][c+i].letter = None

    def render(self):
        for i, row in enumerate(self.grid):
            row_str = ""
            for square in row:
                if row_str == "":
                    row_str = square.get_render_str()
                    continue

                row_str = merge_strings_with_same_num_lines(
                    row_str,
                    square.get_render_str(),
                )

            if i == len(self.grid) - 1:
                print(row_str)
                continue

            row_str = remove_last_line_from_string(row_str)
            print(row_str)

        print()
        for entry in self.entries.values():
            entry.render_clue()