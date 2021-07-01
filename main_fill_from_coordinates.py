"""Main runner class for xwgen"""
from puzzle import Puzzle
from puzzle_filler import PuzzleFiller


def main():
    puzzle = Puzzle(15, 15)
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
    success_words_count, failed_words_count = puzzle_filler.fill_puzzle_using_heuristic(puzzle)
    #puzzle_filler.fill_puzzle_using_backtracking(puzzle)

    puzzle.render()
    print(f"Succeeded: {success_words_count}, Failed: {failed_words_count}")
    puzzle.export_as_ascii("puzz1.out")

if __name__ == "__main__":
    main()
