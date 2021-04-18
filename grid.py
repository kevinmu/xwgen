"""Class representing the crossword grid."""
from typing import List, Tuple

from entry import Entry, Direction
from square import Square


class Grid:
    rows: int
    cols: int
    board: List[List[Square]]
    index: int

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols

        self.board = [[Square() for j in range(cols)] for i in range(rows)]
        self.mark_black_squares([
            (0, 8),
            (1, 8),
            (2, 8),
            (3, 0), (3, 1), (3, 2), (3, 11),
            (4, 5), (4, 10),
            (5, 4), (5, 9), (5, 13), (5, 14),
            (6, 3), (6, 14),
            (7, 7),
        ])

        self.index = 0

        self.number_squares()

    def get_next_index(self):
        self.index += 1
        return self.index

    # Crossword boards have rotational symmetry, so if (r, c) is specified,
    # then both (r, c) and (rows-1-r, cols-1-c) are marked.
    def mark_black_squares(self, coordinates: List[Tuple[int, int]]):
        for coordinate in coordinates:
            r = coordinate[0]
            c = coordinate[1]
            self.board[r][c].is_black = True
            self.board[self.rows-1-r][self.cols-1-c].is_black = True

    def number_squares(self) -> None:
        for r, row in enumerate(self.board):
            for c, square in enumerate(row):
                if square.is_black:
                    continue
                    
                has_empty_square_above = (r == 0 or self.board[r-1][c].is_black)
                has_empty_square_on_left = (c == 0 or self.board[r][c-1].is_black)
                # this represents the start of a new word; give it an index
                if has_empty_square_above or has_empty_square_on_left:
                    square.index = self.get_next_index()

                # specify what kinds of words this square will start
                square.starts_down_word = has_empty_square_above
                square.starts_across_word = has_empty_square_on_left

    def generate_entries_from_numbered_squares(self) -> List[Entry]:
        entries = []
        for r, row in enumerate(self.board):
            for c, square in enumerate(row):
                if square.starts_across_word:
                    entries.append(Entry(square.index, Direction.ACROSS))
                if square.starts_down_word:
                    entries.append(Entry(square.index, Direction.DOWN))

        return entries

    @staticmethod
    def _merge_square_render_strs(str1: str, str2: str) -> str:
        str1_lines = str1.splitlines()
        str2_lines = str2.splitlines()
        assert len(str1_lines) == len(str2_lines), \
            f"{len(str1_lines)} vs {len(str2_lines)}"

        merged_lines = [""] * len(str1_lines)
        for i in range(len(str1_lines)):
            str1_without_right_border = str1_lines[i][:-1]
            merged_lines[i] = str1_without_right_border + str2_lines[i]

        return "\n".join(merged_lines)

    @staticmethod
    def remove_last_line_from_string(s: str) -> str:
        return s[:s.rfind('\n')]

    def render(self):
        for i, row in enumerate(self.board):
            row_str = ""
            for square in row:
                if row_str == "":
                    row_str = square.get_render_str()
                    continue

                row_str = Grid._merge_square_render_strs(
                    row_str,
                    square.get_render_str(),
                )

            if i == len(self.board) - 1:
                print(row_str)
                continue

            row_str = Grid.remove_last_line_from_string(row_str)
            print(row_str)