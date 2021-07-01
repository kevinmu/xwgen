"""Main runner class for xwgen"""
from puzzle import Puzzle
from word_filler import WordFiller


def main():
    puzzle = Puzzle.import_from_ascii("puzz2.out")
    puzzle.render()

    word_filler = WordFiller()
    success_words_count, failed_words_count = word_filler.fill_puzzle_using_heuristic(puzzle)

    puzzle.render()
    print(f"Succeeded: {success_words_count}, Failed: {failed_words_count}")
    puzzle.export_as_ascii("puzz3.out")


if __name__ == "__main__":
    main()
