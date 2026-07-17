"""Download and validate the optional Spread the Word(list) scored lexicon."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "data" / "spreadthewordlist.txt"
SOURCE_PAGE = "https://www.spreadthewordlist.com/"
DOWNLOAD_URL = (
    "https://drive.google.com/uc?export=download&"
    "id=1fbGFn596W047OVOYdrKAxx3OVmwO8UyL"
)
MINIMUM_EXPECTED_ENTRIES = 100_000


def validate_wordlist(path: Path) -> tuple[int, int]:
    entries = 0
    high_quality_entries = 0
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                word, raw_score = line.rsplit(";", 1)
                score = float(raw_score)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid scored entry at line {line_number}"
                ) from exc
            if not word or not 0 <= score <= 100:
                raise ValueError(f"Invalid scored entry at line {line_number}")
            entries += 1
            if score >= 50:
                high_quality_entries += 1

    if entries < MINIMUM_EXPECTED_ENTRIES:
        raise ValueError(
            f"Download contained only {entries:,} entries; expected at least "
            f"{MINIMUM_EXPECTED_ENTRIES:,}"
        )
    return entries, high_quality_entries


def install(output: Path, *, force: bool = False) -> tuple[int, int]:
    output = output.resolve()
    if output.exists() and not force:
        return validate_wordlist(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".part")
    request = Request(
        DOWNLOAD_URL,
        headers={"User-Agent": "XWGen wordlist installer/1.0"},
    )
    try:
        with urlopen(request, timeout=180) as response, partial.open("wb") as target:
            shutil.copyfileobj(response, target)
        result = validate_wordlist(partial)
        os.replace(partial, output)
        return result
    finally:
        partial.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install Spread the Word(list) for local XWGen scoring"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="download again")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        entries, high_quality_entries = install(args.output, force=args.force)
    except Exception as exc:
        print(f"Could not install wordlist: {exc}", file=sys.stderr)
        return 1

    print(
        f"Installed {entries:,} scored entries "
        f"({high_quality_entries:,} scored 50+) at {args.output}"
    )
    print(f"Source: {SOURCE_PAGE}")
    print("License: CC BY-NC-SA 4.0; attribution and noncommercial use required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
