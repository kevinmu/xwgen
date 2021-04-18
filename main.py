"""Main runner class for xwgen"""
from puzzle import Puzzle


def main():
    puzzle = Puzzle.new_puzzle(15, 15)
    puzzle.render()


if __name__ == "__main__":
    main()
