# XWGen roadmap

## AI-assisted lexicon scoring

Build an optional, resumable batch-scoring pipeline for locally supplied word
lists. It should:

- emit a numeric editorial-quality score plus tags such as `abbreviation`,
  `proper-name`, `partial`, `dated`, `offensive`, and `uncertain`;
- use a fixed, human-reviewed rubric and anchor examples;
- validate output counts and resume safely after partial batches;
- evaluate a stratified human-scored sample before promoting new scores;
- preserve a separate user override/banned-word file; and
- avoid requiring an AI call during normal puzzle filling.

AI-produced scores are advisory and should never replace human review of names,
slang, abbreviations, or potentially harmful entries.
