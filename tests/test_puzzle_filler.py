from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from puzzle import Puzzle
from puzzle_filler import FillStatus, PuzzleFiller, SolverConfig


class PuzzleFillerTest(TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.words_file = Path(self.temporary_directory.name) / "words.txt"

    def make_filler(self, words, *, scores=None, **config_overrides):
        self.words_file.write_text("\n".join(words) + "\n", encoding="utf-8")
        config_values = {
            "timeout_seconds": 5,
            "max_nodes_per_restart": 10_000,
            "restarts": 1,
            "random_seed": 0,
        }
        config_values.update(config_overrides)
        return PuzzleFiller(
            self.words_file,
            word_scores=scores,
            config=SolverConfig(**config_values),
        )

    def test_solves_a_fixed_grid_and_applies_it_atomically(self):
        puzzle = Puzzle(3, 3)
        puzzle.initialize()
        puzzle.entries["1A"].clue = "Preserved clue"
        filler = self.make_filler(["ABC", "DEF", "GHI", "ADG", "BEH", "CFI"])

        result = filler.fill_puzzle(puzzle)

        self.assertEqual(FillStatus.SOLVED, result.status)
        self.assertEqual(6, len(result.assignments))
        self.assertEqual("Preserved clue", puzzle.entries["1A"].clue)
        self.assertEqual([], puzzle.validate_puzzle(filler.word_filler))
        self.assertEqual(6, len(set(result.assignments.values())))

    def test_reports_unsatisfiable_without_mutating_the_grid(self):
        puzzle = Puzzle(3, 3)
        puzzle.initialize()
        filler = self.make_filler(["ABC", "DEF", "GHI", "ADG", "BEH"])

        result = filler.fill_puzzle(puzzle)

        self.assertEqual(FillStatus.UNSAT, result.status)
        self.assertTrue(
            all(square.letter is None for row in puzzle.grid for square in row)
        )

    def test_detects_an_impossible_prefilled_pattern(self):
        puzzle = Puzzle(3, 3)
        puzzle.grid[0][0].letter = "Z"
        puzzle.initialize()
        filler = self.make_filler(["ABC", "DEF", "GHI", "ADG", "BEH", "CFI"])

        result = filler.fill_puzzle(puzzle)

        self.assertEqual(FillStatus.UNSAT, result.status)
        self.assertEqual("Z", puzzle.grid[0][0].letter)
        self.assertTrue(
            all(
                square.letter is None
                for row in puzzle.grid
                for square in row
                if square is not puzzle.grid[0][0]
            )
        )

    def test_quality_scores_steer_the_selected_valid_fill(self):
        low_quality_grid = {"AB", "CD", "AC", "BD"}
        high_quality_grid = {"EF", "GH", "EG", "FH"}
        puzzle = Puzzle(2, 2)
        puzzle.initialize()
        scores = {word: 100.0 for word in high_quality_grid}
        filler = self.make_filler(
            sorted(low_quality_grid | high_quality_grid),
            scores=scores,
        )

        result = filler.fill_puzzle(puzzle)

        self.assertEqual(FillStatus.SOLVED, result.status)
        self.assertEqual(high_quality_grid, set(result.assignments.values()))

    def test_budget_cutoff_returns_timeout_and_leaves_the_grid_unchanged(self):
        puzzle = Puzzle(3, 3)
        puzzle.initialize()
        filler = self.make_filler(
            ["ABC", "DEF", "GHI", "ADG", "BEH", "CFI"],
            max_nodes_per_restart=0,
            restarts=2,
        )

        result = filler.fill_puzzle(puzzle)

        self.assertEqual(FillStatus.TIMEOUT, result.status)
        self.assertEqual(2, result.attempts)
        self.assertTrue(
            all(square.letter is None for row in puzzle.grid for square in row)
        )
