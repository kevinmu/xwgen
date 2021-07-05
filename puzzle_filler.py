"""Util class containing logic to fill words."""
from collections import Counter
from typing import List, Tuple

from entry import Entry
from puzzle import Puzzle
from square import Square
from word_filler import WordFiller


class PuzzleFiller:
    word_filler: WordFiller

    def __init__(self, words_file: str = "wordlist.txt"):
        self.word_filler = WordFiller(words_file)

    def fill_puzzle_using_backtracking(self, puzzle: Puzzle) -> None:
        entries_list = puzzle.get_entries_sorted_by_length_asc()
        choices_stack: List[Tuple[Entry, str, List[Square]]] = []

        entry_visit_counter = Counter()
        total_iterations = 0
        while len(entries_list) > 0:
            print(len(entries_list))
            total_iterations += 1
            if total_iterations > 10000:
                print("I TRIED")
                return

            entry = entries_list.pop()
            chosen_answer, affected_squares = \
                self.fill_entry_in_puzzle_using_heuristic(
                    puzzle,
                    entry,
                    entry_visit_counter[entry],
                )
            entry_visit_counter[entry] += 1

            # we've reached a dead-end. Backtrack.
            if chosen_answer == "":
                found_previous_intersecting_entry = False
                entries_list.append(entry)
                # reset the entry_visit_counter because we will hopefully
                # be filling the entry using a different hint the next time.
                entry_visit_counter[entry] = 0

                while not found_previous_intersecting_entry:
                    prev_entry, prev_answer, prev_affected_squares = choices_stack.pop()
                    puzzle.erase_squares(prev_affected_squares)
                    entries_list.append(prev_entry)

                    if prev_entry.intersects_with(entry):
                        found_previous_intersecting_entry = True
                    else:
                        entry_visit_counter[prev_entry] -= 1

                continue

            choices_stack.append((entry, chosen_answer, affected_squares))
        print("DONE?!")
        return

    # Returns a tuple of the chosen answer as well as the squares
    # newly affected by filling in that answer
    def fill_entry_in_puzzle_using_backtracking(
        self,
        puzzle: Puzzle,
        entry: Entry,
        visit_number: int
    ) -> Tuple[str, List[Square]]:
        possible_matches = entry.get_possible_matches(self.word_filler)

        # we've exhausted all possible matches for this entry; fail.
        if visit_number > 20 or len(possible_matches) <= visit_number:
            print(f"COULDN'T FIND VIABLE MATCH FOR {entry.index_str()}")
            return "", []

        next_answer_to_try = possible_matches[visit_number]
        print(f"NEXT ANSWER TO TRY IS {next_answer_to_try}")
        newly_affected_squares = puzzle.fill_entry(entry, next_answer_to_try)

        puzzle.fill_entry(entry, next_answer_to_try)
        return next_answer_to_try, newly_affected_squares

    def fill_puzzle_using_heuristic(self, puzzle: Puzzle) -> Tuple[int, int]:
        failed_words_count = 0
        success_words_count = 0
        entries_list = puzzle.get_entries_sorted_by_fill_priority_desc(self.word_filler)
        while len(entries_list) > 0:
            entry = entries_list[0]
            res, _ = self.fill_entry_in_puzzle_using_heuristic(puzzle, entry, 0)
            if res == "":
                failed_words_count += 1
            else:
                success_words_count += 1

            entries_list = puzzle.get_entries_sorted_by_fill_priority_desc(self.word_filler)
            print("LENGTH OF ENTRIES LIST:", len(entries_list))
        return success_words_count, failed_words_count

    def fill_entry_in_puzzle_using_heuristic(
        self,
        puzzle: Puzzle,
        entry: Entry,
        visit_number: int,
    ) -> Tuple[str, List[Square]]:
        possible_matches = entry.get_possible_matches(self.word_filler)
        if len(possible_matches) == 0:
            return "", []

        answers_with_scores_and_affected_squares = {}

        # maybe i need to do two rounds (i.e., go deeper :()
        for i in range(min(len(possible_matches), 30)):
            random_answer = possible_matches[i]
            newly_affected_squares = puzzle.fill_entry(entry, random_answer)
            newly_affected_entries = \
                set([puzzle.entries[sq.down_entry_parent] for sq in newly_affected_squares]).union(
                    set([puzzle.entries[sq.across_entry_parent] for sq in newly_affected_squares])
                ).difference({entry})

            # TODO(kevin): change heuristic to account for more than just 1 entry?
            num_matches = []
            for newly_affected_entry in newly_affected_entries:
                possible_matches_for_entry = newly_affected_entry.get_possible_matches(self.word_filler)
                num_matches.append(len(possible_matches_for_entry))
            num_matches.sort()

            fill_score = 1000
            if len(num_matches) == 0:
                fill_score = 999
            elif len(num_matches) == 1:
                fill_score = num_matches[0]
            elif num_matches[0] == 0:
                fill_score = 0
            else:
                fill_score = num_matches[0]*0.8 + num_matches[1]*0.2

            answers_with_scores_and_affected_squares[random_answer] = \
                (fill_score, newly_affected_squares)

            # reset the puzzle for the next iteration
            puzzle.erase_squares(newly_affected_squares)

        # sort answers by score
        sorted_answers = list(answers_with_scores_and_affected_squares.keys())
        sorted_answers.sort(key=lambda a: answers_with_scores_and_affected_squares[a][0], reverse=True)
        best_answer = sorted_answers[visit_number] if visit_number < len(sorted_answers) else ""
        if best_answer == "":
            print("TOO MANY VISITS")
            return "", []

        fill_score = answers_with_scores_and_affected_squares[best_answer][0]
        affected_squares = answers_with_scores_and_affected_squares[best_answer][1]

        print(
            f"BEST ANSWER for {entry.index_str()} IS {best_answer} "
            f"with a fill score of {fill_score}",
        )

        puzzle.fill_entry(entry, best_answer)
        return best_answer, affected_squares
