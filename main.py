"""Main runner class for xwgen"""
from entry import Entry
from puzzle import Puzzle
from word_filler import WordFiller


def main():
    puzzle = Puzzle(15, 15)
    puzzle.render()

    word_filler = WordFiller()
    print(word_filler.get_possible_words("A.B.S..."))
    print(word_filler.get_possible_words("..Z."))

    success_words_count, failed_words_count = word_filler.fill_puzzle(puzzle)

    puzzle.render()
    print(f"Succeeded: {success_words_count}, Failed: {failed_words_count}")


if __name__ == "__main__":
    main()
