"""Class representing a full crossword puzzle."""

from typing import List

from grid import Grid
from entry import Entry


class Puzzle:
    grid: Grid
    entries: List[Entry]

    def __init__(self, grid: Grid, entries: List[Entry]):
        self.grid = grid
        self.entries = entries

    @staticmethod
    def new_puzzle(length: int, width: int):
        grid = Grid(length, width)
        entries = grid.generate_entries_from_numbered_squares()
        return Puzzle(grid, entries)

    def render(self):
        self.grid.render()
        print("\n")
        for entry in self.entries:
            entry.render_clue()