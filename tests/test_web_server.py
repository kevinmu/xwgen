from pathlib import Path
from unittest import TestCase

from puzzle import Puzzle
from web_server import (
    PayloadError,
    candidate_response,
    puzzle_from_payload,
    serialize_puzzle,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class WebServerPayloadTest(TestCase):
    def setUp(self):
        self.puzzle = Puzzle.import_from_ascii(str(REPOSITORY_ROOT / "puzz1.out"))
        locks = [[bool(square.letter) for square in row] for row in self.puzzle.grid]
        self.payload = serialize_puzzle(self.puzzle, locked=locks)
        self.payload["clues"] = {
            entry["id"]: entry["clue"] for entry in self.payload["entries"]
        }

    def test_round_trips_grid_metadata_letters_and_clues(self):
        restored = puzzle_from_payload(self.payload)

        self.assertEqual(self.puzzle.rows, restored.rows)
        self.assertEqual(self.puzzle.cols, restored.cols)
        self.assertEqual(self.puzzle.title, restored.title)
        self.assertEqual(
            self.puzzle.entries["1A"].get_current_hint(),
            restored.entries["1A"].get_current_hint(),
        )
        self.assertEqual(self.puzzle.entries["1A"].clue, restored.entries["1A"].clue)

    def test_locked_only_discards_generated_letters(self):
        self.payload["cells"][0][0]["locked"] = False

        restored = puzzle_from_payload(self.payload, locked_only=True)

        self.assertIsNone(restored.grid[0][0].letter)

    def test_rejects_inconsistent_dimensions(self):
        self.payload["rows"] = 14

        with self.assertRaises(PayloadError):
            puzzle_from_payload(self.payload)

    def test_returns_candidates_for_selected_entry(self):
        for column, letter in enumerate("THUS"):
            self.payload["cells"][0][column]["letter"] = letter
            self.payload["cells"][0][column]["locked"] = True
        self.payload["entryId"] = "1A"
        self.payload["limit"] = 10

        response = candidate_response(self.payload)

        self.assertEqual("1A", response["entryId"])
        self.assertEqual("THUS", response["pattern"])
        self.assertIn("THUS", response["candidates"])
