"""Main runner class for xwgen"""
from puzzle import Puzzle
from puzzle_filler import FillStatus, PuzzleFiller


def main() -> int:
    puzzle = Puzzle.import_from_ascii("puzz1.out")
    puzzle.render()

    puzzle_filler = PuzzleFiller()
    result = puzzle_filler.fill_puzzle(puzzle)
    print(result)
    if result.status is not FillStatus.SOLVED:
        return 1

    puzzle.render()
    print("______________________________________")

    failed_entries = puzzle.validate_puzzle(puzzle_filler.word_filler)
    print("NUMBER OF FAILED ENTRIES: ", len(failed_entries))
    for entry in failed_entries:
        print(entry.index_str(), entry.get_current_hint())

    puzzle.export_as_ascii("puzz2.out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
