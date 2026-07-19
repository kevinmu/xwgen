from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from word_filler import WordFiller


class WordFillerTest(TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.words_file = Path(self.temporary_directory.name) / "words.txt"

    def test_builds_bitset_domains_and_filters_nonstandard_entries(self):
        self.words_file.write_text(
            "# comment\ncat\nCAR\nCAN\nAC/DC\nBAD ENTRY\n\n",
            encoding="utf-8",
        )

        word_filler = WordFiller(self.words_file)

        self.assertEqual({"CAN", "CAR", "CAT"}, word_filler.words_set)
        self.assertEqual(2, word_filler.rejected_count)
        self.assertEqual(
            ["CAN", "CAR", "CAT"],
            word_filler.get_possible_words_for_hint("CA."),
        )
        self.assertEqual(["CAR"], word_filler.get_possible_words_for_hint(".AR"))
        self.assertEqual([], word_filler.get_possible_words_for_hint("...."))

    def test_accepts_explicit_quality_scores(self):
        self.words_file.write_text("CAT\nCAR\n", encoding="utf-8")
        word_filler = WordFiller(self.words_file, word_scores={"cat": 7.5})

        cat_id = word_filler.word_id("CAT")

        self.assertIsNotNone(cat_id)
        self.assertEqual(7.5, word_filler.quality_score(3, cat_id))

    def test_reads_crossword_compiler_embedded_scores(self):
        scored_file = Path(self.temporary_directory.name) / "scored.txt"
        scored_file.write_text("CAT;50\nDOG;20\n", encoding="utf-8")

        word_filler = WordFiller(scored_file)

        self.assertTrue(word_filler.is_scored)
        self.assertEqual(2, word_filler.embedded_score_count)
        self.assertEqual(
            50.0,
            word_filler.quality_score(3, word_filler.word_id("CAT")),
        )
        self.assertEqual(
            ["CAT"],
            list(
                word_filler.iter_words(
                    3,
                    word_filler.domain_for_pattern("...", minimum_score=50),
                )
            ),
        )

    def test_rejects_pattern_characters_outside_standard_crossword_fill(self):
        self.words_file.write_text("CAT\n", encoding="utf-8")
        word_filler = WordFiller(self.words_file)

        with self.assertRaises(ValueError):
            word_filler.domain_for_pattern("C-T")
