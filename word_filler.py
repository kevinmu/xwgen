"""Util class containing logic to fill words."""
import random
import re
from typing import Dict, Set, List, Tuple

from entry import Entry, Direction
from puzzle import Puzzle


class WordFiller:
    words_file: str
    words_by_length: Dict[int, List[str]]

    def __init__(self, words_file: str = "wordlist.txt"):
        self.words_file = words_file
        
        # read wordlist file into memory
        with open(self.words_file, "r") as f:
            words_str = f.read()
            words_list = words_str.splitlines()
        
        # populate self.words_by_length
        self.words_by_length = {}
        for word in words_list:
            # represents a comment
            if word.startswith("#"):
                continue
            self.words_by_length.setdefault(len(word), list()).append(word)

    def fill_puzzle(self, puzzle: Puzzle) -> Tuple[int, int]:
        entries_list = []
        for entry in puzzle.entries.values():
            entries_list.append(entry)

        def entry_sort_by_fn(e: Entry) -> int:
            return e.answer_length

        entries_list.sort(key=entry_sort_by_fn, reverse=True)
        failed_words_count = 0
        success_words_count = 0
        for entry in entries_list:
            res = self.fill_entry_in_puzzle(puzzle, entry)
            if res == "":
                failed_words_count += 1
            else:
                success_words_count += 1
        return success_words_count, failed_words_count

    def fill_entry_in_puzzle(self, puzzle: Puzzle, entry: Entry) -> str:
        # find the index
        r_cur = entry.row_in_grid
        c_cur = entry.col_in_grid
        square_cur = puzzle.grid[r_cur][c_cur]

        # construct hint from existing puzzle
        hint = ""
        if entry.direction == Direction.DOWN:
            while not square_cur.is_black:
                hint += "." if square_cur.letter is None else square_cur.letter
                r_cur += 1
                if r_cur == puzzle.rows:
                    break
                square_cur = puzzle.grid[r_cur][c_cur]
        else:
            while not square_cur.is_black:
                hint += "." if square_cur.letter is None else square_cur.letter
                c_cur += 1
                if c_cur == puzzle.cols:
                    break
                square_cur = puzzle.grid[r_cur][c_cur]

        print(f"HINT IS {hint}")
        possible_matches = self.get_possible_words(hint)
        if len(possible_matches) == 0:
            print(f"NOTHING MATCHES HINT {hint}!")
            return ""
        selected_answer = random.choice(possible_matches)
        print(f"SELECTED ANSWER IS {selected_answer}")
        puzzle.fill_entry(entry, selected_answer)
        return selected_answer

    # returns possible matches for the given hint, up to 1000 matches.
    # hint format: ".A..BC..D."
    def get_possible_words(self, hint: str) -> List[str]:
        matches = list()
        word_len = len(hint)
        num_matches = 0
        for word in self.words_by_length[word_len]:
            if re.match(hint, word) is not None:
                matches.append(word)
                num_matches += 1
                if num_matches >= 1000:
                    break
        return matches
