"""Util class containing logic to fill words."""
import random
import re
from typing import Dict, List, Set


class WordFiller:
    words_file: str
    words_by_length: Dict[int, List[str]]
    words_set: Set[str]

    def __init__(self, words_file: str = "wordlist.txt"):
        self.words_file = words_file
        
        # read wordlist file into memory
        with open(self.words_file, "r") as f:
            words_str = f.read()
            words_list = words_str.splitlines()
        
        # populate self.words_by_length
        self.words_by_length = {}
        self.words_set = set()

        for word in words_list:
            # represents a comment
            if word.startswith("#"):
                continue
            self.words_by_length.setdefault(len(word), list()).append(word)
            self.words_set.add(word)

        for k in self.words_by_length:
            random.shuffle(self.words_by_length[k])

    # returns possible matches for the given hint, up to 1000 matches.
    # hint format: ".A..BC..D."
    def get_possible_words_for_hint(self, hint: str) -> List[str]:
        matches = list()
        word_len = len(hint)
        num_matches = 0
        for word in self.words_by_length[word_len]:
            if re.match(hint, word) is not None:
                matches.append(word)
                num_matches += 1
                if num_matches >= 2000:
                    break
        return matches

    def contains_word(self, word: str) -> bool:
        if word in self.words_set:
            print(f"FOUND {word} in set!")
        return word in self.words_set
