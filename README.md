# XWGen

XWGen fills a fixed American-style crossword layout from a word list. Its CSP
solver uses bitset-backed domains, maintained arc consistency, MRV/degree
variable ordering, quality-aware least-constraining values, conflict-directed
backjumping, and deterministic randomized restarts.

The constructor UI can also generate standard-style black-square patterns with
selectable block density.

## Quick start

Python 3.10 or newer is recommended. Core ASCII-grid filling uses only the
standard library. The optional `puzpy` dependency is needed for `.puz` export.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/install_spread_wordlist.py
python -m unittest discover -v
```

Fill the included partially completed puzzle:

```powershell
python fill.py puzz1.out --output filled.out
```

Render a boxed crossword grid directly in the terminal:

```powershell
python fill.py puzz1.out --render
```

Or create a standard `.puz` file that can be opened by a compatible crossword
application:

```powershell
python fill.py puzz1.out --output filled.out --puz-output filled.puz
```

Generate and fill the hard-coded sample layout:

```powershell
python main_fill_from_coordinates.py
```

The command exits with status 0 for a solution, 1 when the grid is proven
unsatisfiable, and 2 when the configured search budget is exhausted. Run
`python fill.py --help` for timeout, restart, seed, rendering, and dictionary
options.

Imported placeholder clues such as `Clue for OLDANSWER` are refreshed when the
solver chooses a different answer. Non-placeholder clue text is preserved.

## Constructor UI

The browser-based constructor provides an editable and numbered crossword grid,
180-degree block symmetry, seed-entry locks, undo/redo, live dictionary
candidates, CSP fill controls, clue editing, ASCII import/export, and `.puz`
export. Its block-layout generator offers airy, classic, and dense presets while
enforcing rotational symmetry, connected white cells, minimum three-letter
entries, and no solid 2x2 block areas.

Install the web dependencies once:

```powershell
cd web
npm install
cd ..
```

Then start the editor and fill engine together:

```powershell
.\run_web.ps1
```

The constructor opens at `http://localhost:3000`. Keep the PowerShell window
open while using it; press `Ctrl+C` there to stop both services.

## Python API

```python
from puzzle import Puzzle
from puzzle_filler import FillStatus, PuzzleFiller, SolverConfig

puzzle = Puzzle.import_from_ascii("puzz1.out")
filler = PuzzleFiller(
    config=SolverConfig(
        timeout_seconds=30,
        max_nodes_per_restart=50_000,
        restarts=4,
        random_seed=0,
    )
)
result = filler.fill_puzzle(puzzle)

if result.status is FillStatus.SOLVED:
    puzzle.export_as_ascii("filled.out")
else:
    print(result.status.value, result.message)
```

The puzzle object is changed only after the solver finds and validates a full
solution. An unsatisfiable or timed-out search leaves the original grid intact.

## Fill quality scores

XWGen prefers the locally installed
[Spread the Word(list)](https://www.spreadthewordlist.com/) scored lexicon.
Install or refresh it with:

```powershell
python scripts/install_spread_wordlist.py --force
```

The dataset is not committed to this repository. It is licensed CC BY-NC-SA
4.0 and may be used in a free product with attribution; reconsider its license
before commercial use. If it is absent, XWGen uses the bundled, permissively
licensed but unscored 2021 Crossword Nexus list.

Spread the Word(list) scores are built directly into its `WORD;SCORE` file.
The solver prioritizes higher-scored candidates, and the constructor displays
those scores in quality-ranked candidate results. You can still supply a UTF-8
TSV or semicolon-separated override file:

```text
# WORD<TAB>SCORE
EXCELLENT	10
CROSSWORDESE	-5
```

```powershell
python fill.py puzz1.out --scores word_scores.tsv --output filled.out
```

Scores are combined with the least-constraining-value score. Higher values are
preferred, while every dictionary candidate remains available if backtracking
needs it. The standard solver accepts A-Z fill; malformed, rebus, numeric, and
slash-separated entries are filtered when the dictionary is loaded. See
[`TODO.md`](TODO.md) for the planned optional AI-assisted scoring pipeline.

## Solver outline

Each across/down entry is a CSP variable. Candidate words are represented as
bits in a Python integer, and `(length, position, letter)` indexes make pattern
matching and propagation fast integer intersections. Crossing arcs enforce
matching letters, singleton propagation enforces unique answers, and the search
uses:

1. maintained arc consistency and forward propagation;
2. minimum-remaining-values with a degree tie-break;
3. quality-aware least-constraining value ordering;
4. conflict sets for non-chronological backjumping; and
5. seeded restarts under explicit node and time budgets.

`FillResult` reports the status, assignments, elapsed time, nodes, backtracks,
backjumps, propagation count, and attempts.
