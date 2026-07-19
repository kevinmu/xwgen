from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from puzzle import Puzzle


class PuzzleTest(TestCase):
    def test_initialize_is_idempotent(self):
        puzzle = Puzzle(3, 3)

        puzzle.initialize()
        first_entries = set(puzzle.entries)
        puzzle.initialize()

        self.assertEqual(first_entries, set(puzzle.entries))
        self.assertEqual(5, puzzle.index)

    def test_rectangular_ascii_round_trip_uses_row_count(self):
        puzzle = Puzzle(2, 3)
        puzzle.title = "Rectangle"
        puzzle.initialize()
        puzzle.grid[0][0].letter = "A"

        with TemporaryDirectory() as directory:
            output_file = Path(directory) / "rectangle.out"
            puzzle.export_as_ascii(str(output_file))
            imported = Puzzle.import_from_ascii(str(output_file))

        self.assertEqual((2, 3), (imported.rows, imported.cols))
        self.assertEqual("A", imported.grid[0][0].letter)
        self.assertEqual(set(puzzle.entries), set(imported.entries))
