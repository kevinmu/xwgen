"""Command-line entry point for filling an ASCII crossword grid."""

from __future__ import annotations

import argparse
from pathlib import Path

from puzzle import Puzzle
from puzzle_filler import FillStatus, PuzzleFiller, SolverConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fill a fixed crossword layout with the CSP solver.",
    )
    parser.add_argument("input", type=Path, help="ASCII puzzle file to fill")
    parser.add_argument(
        "--output", type=Path, help="write the solved ASCII puzzle here"
    )
    parser.add_argument(
        "--wordlist", type=Path, help="plain-text word list (default: wordlist.txt)"
    )
    parser.add_argument(
        "--scores",
        type=Path,
        help="optional tab-separated WORD/SCORE file used for fill quality",
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="overall timeout in seconds"
    )
    parser.add_argument(
        "--nodes-per-restart",
        type=int,
        default=50_000,
        help="decision-node budget for each search attempt",
    )
    parser.add_argument(
        "--restarts", type=int, default=4, help="number of seeded search attempts"
    )
    parser.add_argument("--seed", type=int, default=0, help="base random seed")
    parser.add_argument(
        "--render", action="store_true", help="render the final puzzle in the terminal"
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    puzzle = Puzzle.import_from_ascii(str(args.input))
    config = SolverConfig(
        timeout_seconds=args.timeout,
        max_nodes_per_restart=args.nodes_per_restart,
        restarts=args.restarts,
        random_seed=args.seed,
    )
    filler = PuzzleFiller(
        args.wordlist,
        scores_file=args.scores,
        config=config,
    )
    result = filler.fill_puzzle(puzzle)

    print(
        f"status={result.status.value} elapsed={result.elapsed_seconds:.3f}s "
        f"nodes={result.nodes} backtracks={result.backtracks} "
        f"backjumps={result.backjumps} propagations={result.propagations} "
        f"attempts={result.attempts}"
    )
    if result.message:
        print(result.message)

    if result.status is FillStatus.SOLVED:
        if args.output is not None:
            puzzle.export_as_ascii(str(args.output))
            print(f"wrote {args.output}")
        if args.render:
            puzzle.render()
        return 0
    if result.status is FillStatus.UNSAT:
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
