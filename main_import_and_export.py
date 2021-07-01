"""Main runner class for xwgen"""
from puzzle import Puzzle


def main():
    puzzle = Puzzle.import_from_ascii("puzz1.out")
    puzzle.render()
    puzzle.export_as_ascii("puzz2.out")


if __name__ == "__main__":
    main()
