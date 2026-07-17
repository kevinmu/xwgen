"""Dictionary loading and bitset-backed crossword pattern matching."""

from __future__ import annotations

from pathlib import Path
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Union,
)


ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BUNDLED_WORDS_FILE = Path(__file__).with_name("wordlist.txt")
SPREAD_WORDS_FILE = Path(__file__).with_name("data") / "spreadthewordlist.txt"


class WordFiller:
    """Loads a standard A-Z lexicon and indexes it for fast domain queries.

    Each word length has its own integer ID space.  A domain is represented by
    one Python integer whose set bits are the candidate word IDs.  Positional
    indexes make matching a pattern an intersection of a handful of integers
    instead of a scan through every word of the requested length.
    """

    def __init__(
        self,
        words_file: Optional[Union[str, Path]] = None,
        *,
        word_scores: Optional[Mapping[str, float]] = None,
        scores_file: Optional[Union[str, Path]] = None,
    ) -> None:
        default_words_file = (
            SPREAD_WORDS_FILE if SPREAD_WORDS_FILE.exists() else BUNDLED_WORDS_FILE
        )
        self.words_file = (
            Path(words_file) if words_file is not None else default_words_file
        )

        words_by_length: Dict[int, Set[str]] = {}
        scores: Dict[str, float] = {}
        rejected_count = 0
        embedded_score_count = 0
        with self.words_file.open(
            "r", encoding="utf-8", errors="replace"
        ) as words_handle:
            for raw_line in words_handle:
                raw_word = raw_line.strip()
                if not raw_word or raw_word.startswith("#"):
                    continue
                embedded_score = None
                if ";" in raw_word:
                    raw_word, raw_score = raw_word.rsplit(";", 1)
                    try:
                        embedded_score = float(raw_score)
                    except ValueError:
                        rejected_count += 1
                        continue
                word = raw_word.upper()
                if any(letter not in ALPHABET for letter in word):
                    rejected_count += 1
                    continue
                words_by_length.setdefault(len(word), set()).add(word)
                if embedded_score is not None:
                    scores[word] = embedded_score
                    embedded_score_count += 1

        # Explicit score sources override scores embedded in the word list.
        if scores_file is not None:
            scores.update(self._read_scores(Path(scores_file)))
        if word_scores is not None:
            scores.update(
                {word.upper(): float(score) for word, score in word_scores.items()}
            )

        # Stable ordering makes seeded solver runs reproducible.
        self.words_by_length: Dict[int, List[str]] = {
            length: sorted(words) for length, words in words_by_length.items()
        }
        self.words_set: Set[str] = {
            word for words in self.words_by_length.values() for word in words
        }
        self.rejected_count = rejected_count
        self.embedded_score_count = embedded_score_count
        self.is_scored = bool(scores)
        self.source_name = (
            "Spread the Word(list)"
            if self.words_file.resolve() == SPREAD_WORDS_FILE.resolve()
            else self.words_file.name
        )

        self.word_ids_by_length: Dict[int, Dict[str, int]] = {}
        self.word_scores_by_length: Dict[int, List[float]] = {}
        self.full_masks: Dict[int, int] = {}
        self.position_masks: Dict[int, Sequence[Sequence[int]]] = {}

        for length, words in self.words_by_length.items():
            self.word_ids_by_length[length] = {
                word: word_id for word_id, word in enumerate(words)
            }
            self.word_scores_by_length[length] = [
                scores.get(word, 0.0) for word in words
            ]
            self.full_masks[length] = (1 << len(words)) - 1
            self.position_masks[length] = self._build_position_masks(words, length)

    @staticmethod
    def _read_scores(scores_file: Path) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        with scores_file.open("r", encoding="utf-8") as scores_handle:
            for line_number, raw_line in enumerate(scores_handle, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    separator = "\t" if "\t" in line else ";"
                    word, raw_score = line.rsplit(separator, 1)
                    scores[word.upper()] = float(raw_score)
                except ValueError as exc:
                    raise ValueError(
                        f"Invalid score at {scores_file}:{line_number}; expected "
                        "WORD<TAB>SCORE or WORD;SCORE"
                    ) from exc
        return scores

    @staticmethod
    def _build_position_masks(
        words: Sequence[str], length: int
    ) -> Sequence[Sequence[int]]:
        byte_count = (len(words) + 7) // 8
        raw_masks = [[bytearray(byte_count) for _ in ALPHABET] for _ in range(length)]
        for word_id, word in enumerate(words):
            byte_index = word_id >> 3
            bit = 1 << (word_id & 7)
            for position, letter in enumerate(word):
                raw_masks[position][ord(letter) - ord("A")][byte_index] |= bit

        return tuple(
            tuple(int.from_bytes(mask, "little") for mask in masks_at_position)
            for masks_at_position in raw_masks
        )

    def domain_for_pattern(self, pattern: str) -> int:
        """Return the complete candidate domain for a pattern such as ``.A..E``."""
        pattern = pattern.upper()
        domain = self.full_masks.get(len(pattern), 0)
        if domain == 0:
            return 0

        masks = self.position_masks[len(pattern)]
        for position, letter in enumerate(pattern):
            if letter == ".":
                continue
            if letter not in ALPHABET:
                raise ValueError(
                    f"Unsupported character {letter!r} in pattern {pattern!r}"
                )
            domain &= masks[position][ord(letter) - ord("A")]
            if domain == 0:
                break
        return domain

    def iter_word_ids(self, domain: int) -> Iterator[int]:
        """Yield set-bit indexes from a domain, least-significant bit first."""
        while domain:
            least_significant_bit = domain & -domain
            yield least_significant_bit.bit_length() - 1
            domain ^= least_significant_bit

    def iter_words(self, length: int, domain: int) -> Iterator[str]:
        words = self.words_by_length.get(length, ())
        for word_id in self.iter_word_ids(domain):
            yield words[word_id]

    def word_for_id(self, length: int, word_id: int) -> str:
        return self.words_by_length[length][word_id]

    def word_id(self, word: str) -> Optional[int]:
        word = word.upper()
        return self.word_ids_by_length.get(len(word), {}).get(word)

    def quality_score(self, length: int, word_id: int) -> float:
        return self.word_scores_by_length[length][word_id]

    def mask_for_letter(self, length: int, position: int, letter: str) -> int:
        return self.position_masks[length][position][ord(letter) - ord("A")]

    def supported_letters(
        self, length: int, position: int, domain: int
    ) -> Iterable[int]:
        for letter_index, letter_mask in enumerate(
            self.position_masks[length][position]
        ):
            if domain & letter_mask:
                yield letter_index

    # Backwards-compatible list API used by Entry and older callers.
    def get_possible_words_for_hint(self, hint: str) -> List[str]:
        return list(self.iter_words(len(hint), self.domain_for_pattern(hint)))

    def contains_word(self, word: str) -> bool:
        return word.upper() in self.words_set
