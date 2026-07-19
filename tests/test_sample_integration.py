from pathlib import Path
from unittest import TestCase

from puzzle import Puzzle
from puzzle_filler import FillStatus, PuzzleFiller, SolverConfig


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class SampleIntegrationTest(TestCase):
    def test_fills_the_bundled_partial_fifteen_by_fifteen_puzzle(self):
        puzzle = Puzzle.import_from_ascii(str(REPOSITORY_ROOT / "puzz1.out"))
        filler = PuzzleFiller(
            words_file=REPOSITORY_ROOT / "wordlist.txt",
            config=SolverConfig(
                timeout_seconds=10,
                max_nodes_per_restart=20_000,
                restarts=1,
                random_seed=0,
            )
        )

        result = filler.fill_puzzle(puzzle)

        self.assertEqual(FillStatus.SOLVED, result.status)
        self.assertEqual(74, len(result.assignments))
        self.assertEqual([], puzzle.validate_puzzle(filler.word_filler))
