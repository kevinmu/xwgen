"""Theme-first layout search and fillability preflight."""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import permutations, product
from typing import List, Mapping, Sequence, Tuple

from entry import Direction
from layout_generator import Coordinate, LayoutResult, generate_layout, validate_layout
from puzzle import Puzzle
from puzzle_filler import FillAnalysis, FillStatus, PuzzleFiller, SolverConfig
from word_filler import WordFiller


@dataclass(frozen=True)
class ThemeAnchor:
    row: int
    col: int
    length: int

    def mirrored(self, rows: int, cols: int) -> "ThemeAnchor":
        return ThemeAnchor(
            rows - 1 - self.row,
            cols - self.col - self.length,
            self.length,
        )


@dataclass(frozen=True)
class ThemeLayoutCandidate:
    puzzle: Puzzle
    locked: Tuple[Tuple[bool, ...], ...]
    layout: LayoutResult
    placements: Tuple[Tuple[int, ThemeAnchor, str], ...]
    analysis: FillAnalysis
    verification: str
    probe_message: str


def search_theme_layouts(
    rows: int,
    cols: int,
    answers: Sequence[str],
    *,
    profile: str,
    seed: int,
    word_filler: WordFiller,
    desired_results: int = 3,
    search_attempts: int = 90,
    existing_blocks: Sequence[Sequence[bool]] | None = None,
) -> List[ThemeLayoutCandidate]:
    """Return ranked standard layouts that accommodate and support the themes."""
    rng = random.Random(seed)
    viable: List[ThemeLayoutCandidate] = []
    blocked: List[ThemeLayoutCandidate] = []
    seen_layouts = set()

    if existing_blocks is not None and not validate_layout(existing_blocks):
        existing = _existing_layout_candidates(
            existing_blocks,
            answers,
            profile=profile,
            word_filler=word_filler,
            rng=rng,
        )
        viable.extend(candidate for candidate in existing if candidate.analysis.viable)
        blocked.extend(
            candidate for candidate in existing if not candidate.analysis.viable
        )
        if existing:
            seen_layouts.add(tuple(tuple(row) for row in existing_blocks))

    for _ in range(search_attempts):
        anchors = _choose_anchors(rows, cols, answers, rng)
        if anchors is None:
            continue
        required_white, required_blocks = _placement_constraints(
            rows, cols, anchors
        )
        layout_seed = rng.randrange(0, 2**31)
        try:
            layout = generate_layout(
                rows,
                cols,
                profile=profile,
                seed=layout_seed,
                attempts=5,
                required_white=tuple(required_white),
                required_blocks=tuple(required_blocks),
            )
        except (RuntimeError, ValueError):
            continue
        layout_key = tuple(tuple(row) for row in layout.blocks)
        if layout_key in seen_layouts:
            continue
        seen_layouts.add(layout_key)

        layout_candidates = []
        for assigned_anchors in _assignment_variants(answers, anchors, rng):
            puzzle, locked, placements = _build_puzzle(
                layout, answers, assigned_anchors
            )
            analysis = PuzzleFiller(word_filler=word_filler).analyze_puzzle(puzzle)
            layout_candidates.append(
                ThemeLayoutCandidate(
                    puzzle=puzzle,
                    locked=locked,
                    layout=layout,
                    placements=placements,
                    analysis=analysis,
                    verification="preflight" if analysis.viable else "blocked",
                    probe_message=analysis.message,
                )
            )
        candidate = max(
            layout_candidates,
            key=lambda item: (item.analysis.viable, item.analysis.score),
        )
        if candidate.analysis.viable:
            viable.append(candidate)
            if len(viable) >= max(desired_results * 2, 6):
                break
        elif len(blocked) < desired_results:
            blocked.append(candidate)

    viable.sort(key=lambda candidate: candidate.analysis.score, reverse=True)
    probed: List[ThemeLayoutCandidate] = []
    for candidate in viable[: max(desired_results * 2, 6)]:
        probe_puzzle, _, _ = _build_puzzle(
            candidate.layout,
            answers,
            [anchor for _, anchor, _ in candidate.placements],
        )
        result = PuzzleFiller(
            word_filler=word_filler,
            config=SolverConfig(
                timeout_seconds=1.5,
                max_nodes_per_restart=5_000,
                restarts=1,
                random_seed=candidate.layout.seed,
                quality_cutoffs=(None,),
            ),
        ).fill_puzzle(probe_puzzle)
        verification = {
            FillStatus.SOLVED: "verified",
            FillStatus.TIMEOUT: "promising",
            FillStatus.UNSAT: "blocked",
        }[result.status]
        probed.append(
            ThemeLayoutCandidate(
                puzzle=candidate.puzzle,
                locked=candidate.locked,
                layout=candidate.layout,
                placements=candidate.placements,
                analysis=candidate.analysis,
                verification=verification,
                probe_message=result.message,
            )
        )
        if sum(item.verification == "verified" for item in probed) >= desired_results:
            break

    rank = {"verified": 2, "promising": 1, "preflight": 1, "blocked": 0}
    probed.sort(
        key=lambda candidate: (
            rank[candidate.verification],
            candidate.analysis.score,
        ),
        reverse=True,
    )
    usable = [candidate for candidate in probed if candidate.verification != "blocked"]
    if len(usable) < desired_results:
        usable.extend(
            candidate
            for candidate in viable[len(probed) :]
            if candidate not in usable
        )
    results = usable[:desired_results]
    if len(results) < desired_results:
        results.extend(blocked[: desired_results - len(results)])
    return results


def _existing_layout_candidates(
    blocks: Sequence[Sequence[bool]],
    answers: Sequence[str],
    *,
    profile: str,
    word_filler: WordFiller,
    rng: random.Random,
    assignment_limit: int = 500,
) -> List[ThemeLayoutCandidate]:
    rows = len(blocks)
    cols = len(blocks[0])
    slots_by_length: dict[int, List[ThemeAnchor]] = {}
    for row in range(rows):
        col = 0
        while col < cols:
            while col < cols and blocks[row][col]:
                col += 1
            start = col
            while col < cols and not blocks[row][col]:
                col += 1
            length = col - start
            if length:
                slots_by_length.setdefault(length, []).append(
                    ThemeAnchor(row, start, length)
                )

    if any(len(answer) not in slots_by_length for answer in answers):
        return []
    order = sorted(
        range(len(answers)),
        key=lambda index: (len(slots_by_length[len(answers[index])]), index),
    )
    assignments: List[List[ThemeAnchor]] = []
    selected: dict[int, ThemeAnchor] = {}
    used = set()

    def search(position: int) -> None:
        if len(assignments) >= assignment_limit:
            return
        if position == len(order):
            assignments.append([selected[index] for index in range(len(answers))])
            return
        answer_index = order[position]
        options = list(slots_by_length[len(answers[answer_index])])
        rng.shuffle(options)
        for anchor in options:
            key = (anchor.row, anchor.col, anchor.length)
            if key in used:
                continue
            used.add(key)
            selected[answer_index] = anchor
            search(position + 1)
            used.remove(key)
            if len(assignments) >= assignment_limit:
                return

    search(0)
    block_grid = [list(row) for row in blocks]
    block_count = sum(sum(row) for row in block_grid)
    layout = LayoutResult(
        blocks=block_grid,
        profile=profile,
        block_count=block_count,
        target_block_count=block_count,
        density=block_count / (rows * cols),
        seed=-1,
    )
    candidates = []
    for anchors in assignments:
        puzzle, locked, placements = _build_puzzle(layout, answers, anchors)
        analysis = PuzzleFiller(word_filler=word_filler).analyze_puzzle(puzzle)
        candidates.append(
            ThemeLayoutCandidate(
                puzzle=puzzle,
                locked=locked,
                layout=layout,
                placements=placements,
                analysis=analysis,
                verification="preflight" if analysis.viable else "blocked",
                probe_message=analysis.message,
            )
        )
    candidates.sort(
        key=lambda candidate: (candidate.analysis.viable, candidate.analysis.score),
        reverse=True,
    )
    return candidates[:2]


def theme_crossability(
    candidate: ThemeLayoutCandidate,
) -> Mapping[int, Mapping[str, object]]:
    """Summarize the propagated crossing support for each placed theme."""
    summaries = {}
    for answer_index, anchor, entry_id in candidate.placements:
        entry = candidate.puzzle.entries[entry_id]
        crossing_ids = {
            square.down_entry_parent
            for square in entry.squares
            if square.down_entry_parent
        }
        counts = [
            candidate.analysis.domain_counts[crossing_id]
            for crossing_id in crossing_ids
            if crossing_id in candidate.analysis.domain_counts
        ]
        minimum = min(counts, default=0)
        if not candidate.analysis.viable or minimum == 0:
            label = "Blocked"
        elif minimum < 5:
            label = "Tight"
        elif minimum < 30:
            label = "Constrained"
        else:
            label = "Flexible"
        summaries[answer_index] = {
            "label": label,
            "minimumCrossingDomain": minimum,
            "crossingCount": len(counts),
        }
    return summaries


def _choose_anchors(
    rows: int,
    cols: int,
    answers: Sequence[str],
    rng: random.Random,
) -> List[ThemeAnchor] | None:
    indexed_answers = sorted(
        enumerate(answers), key=lambda item: (-len(item[1]), item[0])
    )
    chosen: dict[int, ThemeAnchor] = {}
    used_slots = set()
    used_rows = set()
    required_white: set[Coordinate] = set()
    required_blocks: set[Coordinate] = set()

    for order_index, (answer_index, answer) in enumerate(indexed_answers):
        length = len(answer)
        anchors = [
            ThemeAnchor(row, col, length)
            for row in range(rows)
            for col in range(cols - length + 1)
            if _legal_horizontal_segments(cols, col, length)
        ]
        rng.shuffle(anchors)
        target_row = (order_index + 1) * (rows - 1) / (len(answers) + 1)

        def anchor_score(anchor: ThemeAnchor) -> float:
            pair_bonus = 0.0
            for prior_index, prior_anchor in chosen.items():
                if len(answers[prior_index]) != length:
                    continue
                if anchor == prior_anchor.mirrored(rows, cols):
                    pair_bonus = 100.0
                    break
            separation = min(
                (abs(anchor.row - row) for row in used_rows), default=0
            )
            center_offset = abs(anchor.col + length / 2 - cols / 2)
            return (
                pair_bonus
                + 0.8 * separation
                - 0.15 * abs(anchor.row - target_row)
                - 0.08 * center_offset
                + 12.0 * rng.random()
            )

        anchors.sort(key=anchor_score, reverse=True)
        selected = None
        for anchor in anchors:
            slot_key = (anchor.row, anchor.col, anchor.length)
            if slot_key in used_slots or anchor.row in used_rows:
                continue
            candidate_white, candidate_blocks = _placement_constraints(
                rows, cols, [anchor]
            )
            if (
                candidate_white & candidate_blocks
                or candidate_white & required_blocks
                or candidate_blocks & required_white
            ):
                continue
            selected = anchor
            required_white.update(candidate_white)
            required_blocks.update(candidate_blocks)
            used_slots.add(slot_key)
            used_rows.add(anchor.row)
            break
        if selected is None:
            return None
        chosen[answer_index] = selected

    return [chosen[index] for index in range(len(answers))]


def _assignment_variants(
    answers: Sequence[str],
    anchors: Sequence[ThemeAnchor],
    rng: random.Random,
    *,
    limit: int = 24,
) -> List[List[ThemeAnchor]]:
    groups: dict[int, List[int]] = {}
    for index, answer in enumerate(answers):
        groups.setdefault(len(answer), []).append(index)
    permutable_groups = [indices for indices in groups.values() if len(indices) > 1]
    if not permutable_groups:
        return [list(anchors)]

    permutations_by_group = [
        list(permutations([anchors[index] for index in indices]))
        for indices in permutable_groups
    ]
    combinations = list(product(*permutations_by_group))
    rng.shuffle(combinations)
    variants = []
    for combination in combinations[:limit]:
        assigned = list(anchors)
        for indices, permuted_anchors in zip(permutable_groups, combination):
            for answer_index, anchor in zip(indices, permuted_anchors):
                assigned[answer_index] = anchor
        variants.append(assigned)
    return variants


def _legal_horizontal_segments(cols: int, col: int, length: int) -> bool:
    left = 0 if col == 0 else col - 1
    end = col + length
    right = 0 if end == cols else cols - end - 1
    return (left == 0 or left >= 3) and (right == 0 or right >= 3)


def _placement_constraints(
    rows: int,
    cols: int,
    anchors: Sequence[ThemeAnchor],
) -> Tuple[set[Coordinate], set[Coordinate]]:
    required_white: set[Coordinate] = set()
    required_blocks: set[Coordinate] = set()
    for anchor in anchors:
        cells = {
            (anchor.row, col)
            for col in range(anchor.col, anchor.col + anchor.length)
        }
        boundaries = set()
        if anchor.col > 0:
            boundaries.add((anchor.row, anchor.col - 1))
        if anchor.col + anchor.length < cols:
            boundaries.add((anchor.row, anchor.col + anchor.length))
        required_white.update(_with_symmetry(rows, cols, cells))
        required_blocks.update(_with_symmetry(rows, cols, boundaries))
    return required_white, required_blocks


def _with_symmetry(
    rows: int,
    cols: int,
    coordinates: Sequence[Coordinate] | set[Coordinate],
) -> set[Coordinate]:
    expanded = set(coordinates)
    expanded.update(
        (rows - 1 - row, cols - 1 - col) for row, col in coordinates
    )
    return expanded


def _build_puzzle(
    layout: LayoutResult,
    answers: Sequence[str],
    anchors: Sequence[ThemeAnchor],
) -> Tuple[
    Puzzle,
    Tuple[Tuple[bool, ...], ...],
    Tuple[Tuple[int, ThemeAnchor, str], ...],
]:
    rows = len(layout.blocks)
    cols = len(layout.blocks[0])
    puzzle = Puzzle(rows, cols)
    locked = [[False for _ in range(cols)] for _ in range(rows)]
    for row in range(rows):
        for col in range(cols):
            puzzle.grid[row][col].is_black = layout.blocks[row][col]
    for answer, anchor in zip(answers, anchors):
        for offset, letter in enumerate(answer):
            puzzle.grid[anchor.row][anchor.col + offset].letter = letter
            locked[anchor.row][anchor.col + offset] = True
    puzzle.initialize()

    placements = []
    for answer_index, (answer, anchor) in enumerate(zip(answers, anchors)):
        entry = next(
            (
                entry
                for entry in puzzle.entries.values()
                if entry.direction is Direction.ACROSS
                and entry.row_in_grid == anchor.row
                and entry.col_in_grid == anchor.col
                and entry.answer_length == len(answer)
            ),
            None,
        )
        if entry is None:
            raise RuntimeError("Generated layout lost a required theme slot")
        entry.clue = ""
        placements.append((answer_index, anchor, entry.index_str()))
    return (
        puzzle,
        tuple(tuple(row) for row in locked),
        tuple(placements),
    )
