"""Main runner class for xwgen"""
from puzzle import Puzzle
from puzzle_filler import PuzzleFiller


def main():
    puzzle = Puzzle.import_from_ascii("puzz2.out")
    puzzle.render()

    puzzle_filler = PuzzleFiller()
    puzzle_filler.fill_puzzle_using_heuristic(puzzle)

    puzzle.render()

    failed_entries = puzzle.validate_puzzle(puzzle_filler.word_filler)
    print("NUMBER OF FAILED ENTRIES: ", len(failed_entries))
    for entry in failed_entries:
        print(entry.index_str(), entry.get_current_hint())

    puzzle.export_as_ascii("puzz3.out")


if __name__ == "__main__":
    main()
