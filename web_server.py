"""Local JSON API used by the XWGen constructor interface."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlparse

from layout_generator import generate_layout
from puzzle import Puzzle
from puzzle_filler import QUALITY_MODE_CUTOFFS, PuzzleFiller, SolverConfig
from theme_layout import search_theme_layouts, theme_crossability
from word_filler import WordFiller


REPOSITORY_ROOT = Path(__file__).resolve().parent
DEFAULT_SAMPLE = REPOSITORY_ROOT / "puzz1.out"
MAX_REQUEST_BYTES = 2_000_000
MAX_GRID_SIZE = 25


class PayloadError(ValueError):
    """Raised when a browser request does not describe a valid grid."""


def serialize_puzzle(
    puzzle: Puzzle,
    *,
    locked: Optional[Sequence[Sequence[bool]]] = None,
) -> Dict[str, Any]:
    cells: List[List[Dict[str, Any]]] = []
    for row_index, row in enumerate(puzzle.grid):
        serialized_row = []
        for col_index, square in enumerate(row):
            is_locked = bool(
                locked is not None
                and row_index < len(locked)
                and col_index < len(locked[row_index])
                and locked[row_index][col_index]
            )
            serialized_row.append(
                {
                    "black": square.is_black,
                    "letter": square.letter or "",
                    "locked": is_locked and not square.is_black,
                    "number": square.index,
                }
            )
        cells.append(serialized_row)

    entries = []
    for entry in puzzle.entries.values():
        entries.append(
            {
                "id": entry.index_str(),
                "number": entry.index,
                "direction": entry.direction.value,
                "row": entry.row_in_grid,
                "col": entry.col_in_grid,
                "length": entry.answer_length,
                "answer": entry.get_current_hint().replace(".", ""),
                "pattern": entry.get_current_hint(),
                "clue": entry.clue or "",
            }
        )

    return {
        "rows": puzzle.rows,
        "cols": puzzle.cols,
        "title": puzzle.title,
        "author": puzzle.author,
        "copyright": puzzle.copyright,
        "note": puzzle.note,
        "cells": cells,
        "entries": entries,
    }


def puzzle_from_payload(
    payload: Mapping[str, Any],
    *,
    locked_only: bool = False,
) -> Puzzle:
    try:
        rows = int(payload["rows"])
        cols = int(payload["cols"])
        cells = payload["cells"]
    except (KeyError, TypeError, ValueError) as exc:
        raise PayloadError("Grid dimensions and cells are required") from exc

    if not (3 <= rows <= MAX_GRID_SIZE and 3 <= cols <= MAX_GRID_SIZE):
        raise PayloadError(f"Grid dimensions must be between 3 and {MAX_GRID_SIZE}")
    if not isinstance(cells, list) or len(cells) != rows:
        raise PayloadError("Cell rows do not match the grid height")

    puzzle = Puzzle(rows, cols)
    puzzle.title = str(payload.get("title", ""))[:255]
    puzzle.author = str(payload.get("author", ""))[:255]
    puzzle.copyright = str(payload.get("copyright", ""))[:255]
    puzzle.note = str(payload.get("note", ""))[:2000]

    for row_index, row in enumerate(cells):
        if not isinstance(row, list) or len(row) != cols:
            raise PayloadError("Cell columns do not match the grid width")
        for col_index, raw_cell in enumerate(row):
            if not isinstance(raw_cell, Mapping):
                raise PayloadError("Each cell must be an object")
            square = puzzle.grid[row_index][col_index]
            square.is_black = bool(raw_cell.get("black", False))
            if square.is_black:
                continue
            if locked_only and not bool(raw_cell.get("locked", False)):
                continue
            letter = str(raw_cell.get("letter", "")).strip().upper()
            if letter:
                if len(letter) != 1 or not letter.isascii() or not letter.isalpha():
                    raise PayloadError("Letters must be a single A-Z character")
                square.letter = letter

    puzzle.initialize()
    clues = payload.get("clues", {})
    if isinstance(clues, Mapping):
        for entry_id, clue in clues.items():
            if entry_id in puzzle.entries:
                puzzle.entries[entry_id].clue = str(clue)[:2000]
    return puzzle


def locked_matrix(payload: Mapping[str, Any]) -> List[List[bool]]:
    return [
        [bool(cell.get("locked", False)) for cell in row]
        for row in payload.get("cells", [])
    ]


def shape_warnings(puzzle: Puzzle) -> List[str]:
    warnings = []
    short_entries = [
        entry.index_str()
        for entry in puzzle.entries.values()
        if entry.answer_length < 3
    ]
    if short_entries:
        warnings.append(
            "American-style grids normally avoid one- and two-letter entries: "
            + ", ".join(short_entries[:8])
            + ("…" if len(short_entries) > 8 else "")
        )
    unchecked = sum(
        1
        for row in puzzle.grid
        for square in row
        if not square.is_black
        and not (square.across_entry_parent and square.down_entry_parent)
    )
    if unchecked:
        warnings.append(f"{unchecked} white cells are not checked in both directions")
    return warnings


_candidate_dictionary: Optional[WordFiller] = None


def candidate_dictionary() -> WordFiller:
    global _candidate_dictionary
    if _candidate_dictionary is None:
        _candidate_dictionary = WordFiller()
    return _candidate_dictionary


def candidate_response(payload: Mapping[str, Any]) -> Dict[str, Any]:
    puzzle = puzzle_from_payload(payload, locked_only=True)
    current_puzzle = puzzle_from_payload(payload)
    entry_id = str(payload.get("entryId", ""))
    entry = puzzle.entries.get(entry_id)
    current_entry = current_puzzle.entries.get(entry_id)
    if entry is None or current_entry is None:
        raise PayloadError("The selected entry no longer exists")

    dictionary = candidate_dictionary()
    domain = dictionary.domain_for_pattern(entry.get_current_hint())
    requested_limit = int(payload.get("limit", 40))
    limit = max(1, min(requested_limit, 100))
    candidates = [
        {
            "word": dictionary.word_for_id(entry.answer_length, word_id),
            "score": dictionary.quality_score(entry.answer_length, word_id),
        }
        for word_id in dictionary.iter_word_ids(domain)
    ]
    candidates.sort(key=lambda candidate: (-candidate["score"], candidate["word"]))
    current_answer = current_entry.get_current_hint()
    selected_word = None
    if "." not in current_answer:
        current_word_id = dictionary.word_id(current_answer)
        selected_word = {
            "word": current_answer,
            "score": (
                dictionary.quality_score(current_entry.answer_length, current_word_id)
                if current_word_id is not None
                else None
            ),
            "inLexicon": current_word_id is not None,
        }
    return {
        "entryId": entry_id,
        "pattern": entry.get_current_hint(),
        "total": len(candidates),
        "candidates": candidates[:limit],
        "selectedWord": selected_word,
        "lexicon": lexicon_metadata(dictionary),
    }


def lexicon_metadata(dictionary: Optional[WordFiller] = None) -> Dict[str, Any]:
    active_dictionary = dictionary or candidate_dictionary()
    return {
        "source": active_dictionary.source_name,
        "scored": active_dictionary.is_scored,
        "entries": len(active_dictionary.words_set),
        "license": (
            "CC BY-NC-SA 4.0"
            if active_dictionary.source_name == "Spread the Word(list)"
            else "Bundled fallback"
        ),
    }


def fill_response(payload: Mapping[str, Any]) -> Dict[str, Any]:
    puzzle = puzzle_from_payload(payload, locked_only=True)
    options = payload.get("options", {})
    if not isinstance(options, Mapping):
        options = {}
    quality_mode = str(options.get("qualityMode", "balanced")).lower()
    if quality_mode not in QUALITY_MODE_CUTOFFS:
        raise PayloadError("Fill quality mode must be balanced, strict, or open")

    config = SolverConfig(
        timeout_seconds=max(1.0, min(float(options.get("timeout", 20)), 120.0)),
        max_nodes_per_restart=max(
            100, min(int(options.get("nodesPerRestart", 50_000)), 1_000_000)
        ),
        restarts=max(1, min(int(options.get("restarts", 4)), 20)),
        random_seed=int(options.get("seed", 0)),
        quality_cutoffs=QUALITY_MODE_CUTOFFS[quality_mode],
    )
    result = PuzzleFiller(
        word_filler=candidate_dictionary(),
        config=config,
    ).fill_puzzle(puzzle)
    response = serialize_puzzle(puzzle, locked=locked_matrix(payload))
    response["result"] = {
        "status": result.status.value,
        "message": result.message,
        "nodes": result.nodes,
        "backtracks": result.backtracks,
        "backjumps": result.backjumps,
        "propagations": result.propagations,
        "attempts": result.attempts,
        "elapsedSeconds": result.elapsed_seconds,
        "minimumScore": result.minimum_score,
        "qualityMode": quality_mode,
    }
    response["warnings"] = shape_warnings(puzzle)
    return response


def layout_response(payload: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        rows = int(payload.get("rows", 15))
        cols = int(payload.get("cols", 15))
        seed = int(payload.get("seed", 0))
    except (TypeError, ValueError) as exc:
        raise PayloadError("Layout dimensions and seed must be integers") from exc
    profile = str(payload.get("profile", "classic")).lower()
    try:
        generated = generate_layout(
            rows,
            cols,
            profile=profile,
            seed=seed,
        )
    except (RuntimeError, ValueError) as exc:
        raise PayloadError(str(exc)) from exc

    puzzle = Puzzle(rows, cols)
    puzzle.title = str(payload.get("title", "Untitled crossword"))[:255]
    puzzle.author = str(payload.get("author", ""))[:255]
    puzzle.copyright = str(payload.get("copyright", ""))[:255]
    puzzle.note = str(payload.get("note", ""))[:2000]
    for row in range(rows):
        for col in range(cols):
            puzzle.grid[row][col].is_black = generated.blocks[row][col]
    puzzle.initialize()

    response = serialize_puzzle(puzzle)
    response["layout"] = {
        "profile": generated.profile,
        "blockCount": generated.block_count,
        "targetBlockCount": generated.target_block_count,
        "density": generated.density,
        "seed": generated.seed,
    }
    response["warnings"] = shape_warnings(puzzle)
    return response


def theme_layouts_response(payload: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        rows = int(payload.get("rows", 15))
        cols = int(payload.get("cols", 15))
        seed = int(payload.get("seed", 0))
    except (TypeError, ValueError) as exc:
        raise PayloadError("Theme layout dimensions and seed must be integers") from exc
    if not (7 <= rows <= MAX_GRID_SIZE and 7 <= cols <= MAX_GRID_SIZE):
        raise PayloadError(f"Theme layouts require dimensions between 7 and {MAX_GRID_SIZE}")
    profile = str(payload.get("profile", "classic")).lower()
    raw_answers = payload.get("answers", [])
    if not isinstance(raw_answers, list) or not 4 <= len(raw_answers) <= 6:
        raise PayloadError("Provide between four and six theme answers")
    answers = []
    for raw_answer in raw_answers:
        answer = "".join(
            letter for letter in str(raw_answer).upper() if "A" <= letter <= "Z"
        )
        if not 3 <= len(answer) <= cols:
            raise PayloadError(
                f"Theme answers must contain between 3 and {cols} letters"
            )
        answers.append(answer)
    if len(set(answers)) != len(answers):
        raise PayloadError("Theme answers must be unique")

    existing_blocks = None
    raw_cells = payload.get("cells")
    if isinstance(raw_cells, list) and len(raw_cells) == rows:
        if all(
            isinstance(row, list)
            and len(row) == cols
            and all(isinstance(cell, Mapping) for cell in row)
            for row in raw_cells
        ):
            existing_blocks = [
                [bool(cell.get("black", False)) for cell in row]
                for row in raw_cells
            ]

    candidates = search_theme_layouts(
        rows,
        cols,
        answers,
        profile=profile,
        seed=seed,
        word_filler=candidate_dictionary(),
        desired_results=3,
        search_attempts=max(
            30, min(int(payload.get("searchAttempts", 150)), 300)
        ),
        existing_blocks=existing_blocks,
    )
    title = str(payload.get("title", "Untitled crossword"))[:255]
    author = str(payload.get("author", ""))[:255]
    serialized_candidates = []
    for index, candidate in enumerate(candidates):
        serialized = serialize_puzzle(candidate.puzzle, locked=candidate.locked)
        serialized["title"] = title
        serialized["author"] = author
        serialized["id"] = f"theme-layout-{index + 1}-{candidate.layout.seed}"
        serialized["layout"] = {
            "profile": candidate.layout.profile,
            "blockCount": candidate.layout.block_count,
            "targetBlockCount": candidate.layout.target_block_count,
            "density": candidate.layout.density,
            "seed": candidate.layout.seed,
            "currentLayout": candidate.layout.seed == -1,
        }
        crossability = theme_crossability(candidate)
        serialized["placements"] = [
            {
                "answerIndex": answer_index,
                "answer": answers[answer_index],
                "entryId": entry_id,
                "row": anchor.row,
                "col": anchor.col,
                "length": anchor.length,
                **crossability[answer_index],
            }
            for answer_index, anchor, entry_id in candidate.placements
        ]
        rating = {
            "verified": "Verified fill",
            "promising": "Promising",
            "preflight": "Promising",
            "blocked": "Blocked",
        }[candidate.verification]
        serialized["analysis"] = {
            "verification": candidate.verification,
            "rating": rating,
            "viable": candidate.analysis.viable
            and candidate.verification != "blocked",
            "score": round(min(99.0, candidate.analysis.score * 10), 1),
            "minimumDomain": candidate.analysis.minimum_domain,
            "averageDomain": round(candidate.analysis.average_domain, 1),
            "message": candidate.probe_message,
            "tightEntries": [
                {"id": entry_id, "pattern": pattern, "candidates": count}
                for entry_id, pattern, count in candidate.analysis.tight_entries
            ],
        }
        serialized_candidates.append(serialized)

    return {
        "answers": answers,
        "candidates": serialized_candidates,
        "message": (
            "Choose a preflighted layout below."
            if serialized_candidates
            else "No standard layout could accommodate this answer set. Try an alternate length or fewer theme answers."
        ),
    }


class XWGenRequestHandler(BaseHTTPRequestHandler):
    server_version = "XWGen/1.0"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json({"ok": True, "lexicon": lexicon_metadata()})
            return
        if path == "/api/sample":
            puzzle = Puzzle.import_from_ascii(str(DEFAULT_SAMPLE))
            locks = [
                [bool(square.letter) for square in row]
                for row in puzzle.grid
            ]
            response = serialize_puzzle(puzzle, locked=locks)
            response["warnings"] = shape_warnings(puzzle)
            self._send_json(response)
            return
        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/candidates":
                self._send_json(candidate_response(payload))
                return
            if path == "/api/fill":
                self._send_json(fill_response(payload))
                return
            if path == "/api/layout":
                self._send_json(layout_response(payload))
                return
            if path == "/api/theme-layouts":
                self._send_json(theme_layouts_response(payload))
                return
            if path == "/api/export/puz":
                puzzle = puzzle_from_payload(payload)
                data = puzzle.to_puz_puzzle().tobytes()
                self.send_response(HTTPStatus.OK)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/x-crossword")
                self.send_header(
                    "Content-Disposition", 'attachment; filename="xwgen-puzzle.puz"'
                )
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except PayloadError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except (TypeError, ValueError) as exc:
            self._send_json({"error": f"Invalid request: {exc}"}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - last-resort HTTP boundary
            self.log_error("request failed: %s", exc)
            self._send_json(
                {"error": "The constructor could not complete that request"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _read_json(self) -> Mapping[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise PayloadError("Invalid content length") from exc
        if length <= 0 or length > MAX_REQUEST_BYTES:
            raise PayloadError("Request body is empty or too large")
        try:
            payload = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PayloadError("Request body must be valid JSON") from exc
        if not isinstance(payload, Mapping):
            raise PayloadError("Request body must be an object")
        return payload

    def _send_json(
        self,
        payload: Mapping[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_cors_headers(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin.startswith("http://localhost:") or origin.startswith(
            "http://127.0.0.1:"
        ):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[xwgen] {self.address_string()} {format % args}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the XWGen constructor API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), XWGenRequestHandler)
    print(f"XWGen API listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
