"""Main runner class for xwgen"""
from puzzle import Puzzle
from puzzle_filler import PuzzleFiller


def main():
    puzzle = Puzzle.import_from_ascii("puzz2.out")
    puzzle.render()

    puzzle_filler = PuzzleFiller()
    success_words_count, failed_words_count = puzzle_filler.fill_puzzle_using_heuristic(puzzle)

    puzzle.render()
    print(f"Succeeded: {success_words_count}, Failed: {failed_words_count}")
    puzzle.export_as_ascii("puzz3.out")


if __name__ == "__main__":
    main()
