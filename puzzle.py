"""Class representing the crossword grid."""
from typing import List, Tuple, Dict

from entry import Entry, Direction
from square import Square
from string_utils import merge_strings_with_same_num_lines
from string_utils import remove_last_line_from_string
from word_filler import WordFiller

class Puzzle:
    rows: int
    cols: int
    grid: List[List[Square]]
    index: int
    entries: Dict[str, Entry]

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols

        self.grid = [[Square() for _ in range(cols)] for _ in range(rows)]
        self.index = 0

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

    def mark_black_square(self, coordinate: Tuple[int, int]):
        return self.mark_black_squares([coordinate])

    # setup function to be run after setting all black squares
    def initialize(self) -> None:
        self._number_squares()
        self.entries = self._generate_entries_from_numbered_squares()

    def _number_squares(self) -> None:
        for r, row in enumerate(self.grid):
            for c, square in enumerate(row):
                if square.is_black:
                    continue
                    
                has_black_square_above = (r == 0 or self.grid[r - 1][c].is_black)
                has_black_square_on_left = (c == 0 or self.grid[r][c - 1].is_black)
                # this represents the start of a new word; give it an index
                if has_black_square_above or has_black_square_on_left:
                    square.index = self.get_next_index()

                # specify what kinds of words this square will start
                square.starts_down_word = has_black_square_above
                square.starts_across_word = has_black_square_on_left

    def _generate_entries_from_numbered_squares(self) -> Dict[str, Entry]:
        entries = {}
        for r, row in enumerate(self.grid):
            for c, square in enumerate(row):
                squares_for_entry = []
                if square.starts_across_word:
                    i = 0
                    while c + i < self.cols and not self.grid[r][c+i].is_black:
                        squares_for_entry.append(self.grid[r][c+i])
                        i += 1

                    entry = Entry(
                        square.index,
                        Direction.ACROSS,
                        r,
                        c,
                        i,
                        squares=squares_for_entry,
                    )
                    entries[entry.index_str()] = entry
                    for square_for_entry in squares_for_entry:
                        square_for_entry.across_entry_parent = entry.index_str()

                if square.starts_down_word:
                    i = 0
                    squares_for_entry = []
                    while r + i < self.rows and not self.grid[r+i][c].is_black:
                        squares_for_entry.append(self.grid[r+i][c])
                        i += 1

                    entry = Entry(
                        square.index,
                        Direction.DOWN,
                        r,
                        c,
                        i,
                        squares=squares_for_entry
                    )
                    entries[entry.index_str()] = entry
                    for square_for_entry in squares_for_entry:
                        square_for_entry.down_entry_parent = entry.index_str()

        return entries

    def get_entries_sorted_by_length_asc(self) -> List[Entry]:
        entries = self.get_entries_sorted_by_length_desc()
        entries.reverse()
        return entries

    def get_entries_sorted_by_length_desc(self) -> List[Entry]:
        entries_list = []
        for entry in self.entries.values():
            entries_list.append(entry)

        # Heuristic #1: fill in longer words first
        #               because they are harder to fill.
        def entry_sort_by_fn(e: Entry) -> int:
            return e.answer_length

        entries_list.sort(key=entry_sort_by_fn, reverse=True)
        return entries_list

    def get_entries_sorted_by_num_possible_matches_asc(
        self,
        word_filler: WordFiller,
    ) -> List[Entry]:
        entries_list = []
        for entry in self.entries.values():
            entries_list.append(entry)

        # Heuristic #2: fill in words with fewer possibilities first
        #               because they are harder to fill.
        def entry_sort_by_fn(e: Entry) -> int:
            return e.get_num_possible_matches(word_filler)

        entries_list.sort(key=entry_sort_by_fn)
        return entries_list

    def get_entries_sorted_by_index_str_asc(self) -> List[Entry]:
        entries_list = []
        for entry in self.entries.values():
            entries_list.append(entry)

        # Heuristic #1: fill in longer words first
        #               because they are harder to fill.
        def entry_sort_by_fn(e: Entry) -> int:
            return e.index

        entries_list.sort(key=entry_sort_by_fn, reverse=True)
        return entries_list

    # Fills an entry of the puzzle with a provided guess.
    # Returns a list of the affected squares.
    def fill_entry(self, entry: Entry, guess: str) -> List[Square]:
        assert len(guess) == entry.answer_length, \
            f"Answer {guess} has length {len(guess)}, but entry " \
            f"{entry.index_str()} has length {entry.answer_length}"

        newly_affected_squares = []
        r = entry.row_in_grid
        c = entry.col_in_grid
        if entry.direction == Direction.DOWN:
            for i, letter in enumerate(guess):
                square = self.grid[r + i][c]
                if square.letter != letter:
                    square.letter = letter
                    newly_affected_squares.append(square)
        else:
            for i, letter in enumerate(guess):
                square = self.grid[r][c+i]
                if square.letter != letter:
                    square.letter = letter
                    newly_affected_squares.append(square)

        return newly_affected_squares

    # Idempotently erases a letter from a list of Squares.
    def erase_squares(self, squares: List[Square]) -> None:
        for square in squares:
            square.letter = None

    """
    Functions to import/export/print the puzzle. 
    """

    def export_as_ascii(self, outfile: str):
        puzzle_ascii = ""
        for r in range(self.rows):
            for c in range(self.cols):
                sq = self.grid[r][c]
                if sq.is_black:
                    puzzle_ascii += "*"
                elif sq.letter is None:
                    puzzle_ascii += "-"
                else:
                    puzzle_ascii += sq.letter
            puzzle_ascii += "\n"
        with open(outfile, "w") as f:
            f.write(puzzle_ascii)

    @staticmethod
    def import_from_ascii(infile: str) -> 'Puzzle':
        with open(infile, "r") as f:
            puzzle_ascii = f.read()

        lines = puzzle_ascii.splitlines()
        rows = len(lines)
        cols = len(lines[0])
        puzzle = Puzzle(rows=rows, cols=cols)
        for r, line in enumerate(lines):
            for c, letter in enumerate(line):
                if letter == "*":
                    puzzle.mark_black_square((r, c))
                elif letter != "-":
                    puzzle.grid[r][c].letter = letter

        puzzle.initialize()
        return puzzle

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