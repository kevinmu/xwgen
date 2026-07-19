"""Main runner class for xwgen"""
from puzzle import Puzzle
from puzzle_filler import FillStatus, PuzzleFiller


def main() -> int:
    puzzle = Puzzle(15, 15)
    puzzle.title = "Test Puzzle #1"
    puzzle.author = "Kevin Mu"

    '''puzzle.mark_black_squares([
        (0, 8),
        (1, 8),
        (2, 8),
        (3, 0), (3, 1), (3, 2), (3, 11),
        (4, 5), (4, 10),
        (5, 4), (5, 9), (5, 13), (5, 14),
        (6, 3), (6, 14),
        (7, 7),
    ])'''

    puzzle.mark_black_squares([
        (0, 4), (0, 9),
        (1, 4), (1, 9),
        (2, 4),
        (3, 6), (3, 12), (3, 13), (3, 14),
        (4, 11),
        (5, 0), (5, 1), (5, 2), (5, 3), (5, 7), (5, 8),
        (6, 0),
        (7, 4), (7, 5), (7, 9), (7, 10)
    ])
    puzzle.initialize()
    puzzle.render()

    puzzle_filler = PuzzleFiller()
    result = puzzle_filler.fill_puzzle(puzzle)
    print(result)
    if result.status is not FillStatus.SOLVED:
        return 1

    puzzle.render()
    puzzle.export_as_ascii("puzz1.out")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
