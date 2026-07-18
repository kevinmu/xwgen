"""Generate conventional rotationally symmetric crossword block layouts."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


Coordinate = Tuple[int, int]
BlockGrid = List[List[bool]]


PROFILE_DENSITIES: Dict[str, float] = {
    "airy": 0.12,
    "classic": 0.145,
    "dense": 0.17,
}


@dataclass(frozen=True)
class LayoutResult:
    blocks: BlockGrid
    profile: str
    block_count: int
    target_block_count: int
    density: float
    seed: int


def generate_layout(
    rows: int,
    cols: int,
    *,
    profile: str = "classic",
    seed: int = 0,
    attempts: int = 20,
    required_white: Sequence[Coordinate] = (),
    required_blocks: Sequence[Coordinate] = (),
) -> LayoutResult:
    """Return a standard-style block layout for a rectangular crossword.

    The generator preserves 180-degree symmetry, keeps every white square in
    the same connected component, forbids one- and two-letter slots, and avoids
    solid 2x2 block areas. Multiple valid candidates are sampled and the most
    evenly distributed one is returned.
    """
    if rows < 7 or cols < 7:
        raise ValueError("Layout generation requires at least a 7 by 7 grid")
    if rows > 25 or cols > 25:
        raise ValueError("Layout generation supports grids up to 25 by 25")
    if profile not in PROFILE_DENSITIES:
        raise ValueError(f"Unknown block profile: {profile}")
    if attempts < 1:
        raise ValueError("attempts must be positive")

    white_constraints = _symmetric_coordinates(rows, cols, required_white)
    block_constraints = _symmetric_coordinates(rows, cols, required_blocks)
    if white_constraints & block_constraints:
        raise ValueError("Layout constraints require the same square to be white and black")

    target = round(rows * cols * PROFILE_DENSITIES[profile])
    # Even-sized grids cannot contain a self-symmetric center square, so their
    # block counts must be even under 180-degree symmetry.
    if rows * cols % 2 == 0 and target % 2:
        target += 1
    center = (rows // 2, cols // 2) if rows % 2 and cols % 2 else None
    if center in white_constraints and target % 2:
        target += 1
    elif center in block_constraints and target % 2 == 0:
        target += 1
    if len(block_constraints) > target:
        target = len(block_constraints)
        if center is not None and (center in block_constraints) != bool(target % 2):
            target += 1

    best_grid = None
    best_score = float("-inf")
    rng = random.Random(seed)
    for _ in range(attempts):
        candidate = _construct_candidate(
            rows,
            cols,
            target,
            rng,
            required_white=white_constraints,
            required_blocks=block_constraints,
        )
        if candidate is None:
            continue
        score = _aesthetic_score(candidate) + rng.random() * 0.001
        if score > best_score:
            best_grid = candidate
            best_score = score

    if best_grid is None:
        raise RuntimeError(
            "Could not generate a valid layout; try another density or variation"
        )

    block_count = sum(sum(row) for row in best_grid)
    return LayoutResult(
        blocks=best_grid,
        profile=profile,
        block_count=block_count,
        target_block_count=target,
        density=block_count / (rows * cols),
        seed=seed,
    )


def validate_layout(blocks: Sequence[Sequence[bool]]) -> List[str]:
    """Return rule violations for a proposed American-style block layout."""
    if not blocks or not blocks[0]:
        return ["The layout is empty"]
    cols = len(blocks[0])
    if any(len(row) != cols for row in blocks):
        return ["The layout is not rectangular"]

    violations = []
    if not _is_rotationally_symmetric(blocks):
        violations.append("Blocks are not 180-degree rotationally symmetric")
    if _has_short_slots(blocks):
        violations.append("The layout contains an entry shorter than three letters")
    if not _white_cells_are_connected(blocks):
        violations.append("White cells are not connected")
    if _has_two_by_two_blocks(blocks):
        violations.append("The layout contains a solid 2x2 block area")
    return violations


def _construct_candidate(
    rows: int,
    cols: int,
    target: int,
    rng: random.Random,
    *,
    required_white: Sequence[Coordinate] = (),
    required_blocks: Sequence[Coordinate] = (),
) -> BlockGrid | None:
    blocks = [[False for _ in range(cols)] for _ in range(rows)]
    white_constraints = set(required_white)
    block_constraints = set(required_blocks)
    for row, col in block_constraints:
        blocks[row][col] = True
    if not _repair_short_slots(blocks, white_constraints):
        return None
    if not _is_valid_partial(blocks):
        return None
    representatives: List[Tuple[Coordinate, ...]] = []
    center_pair: Tuple[Coordinate, ...] | None = None

    for row in range(rows):
        for col in range(cols):
            opposite = (rows - 1 - row, cols - 1 - col)
            coordinate = (row, col)
            if coordinate < opposite:
                representatives.append((coordinate, opposite))
            elif coordinate == opposite:
                center_pair = (coordinate,)

    block_count = sum(sum(row) for row in blocks)
    if target % 2:
        if center_pair is None:
            return None
        if not blocks[center_pair[0][0]][center_pair[0][1]]:
            if center_pair[0] in white_constraints:
                return None
            _set_pair(blocks, center_pair, True)
            if not _is_valid_partial(blocks):
                return None
            block_count += 1

    rng.shuffle(representatives)
    for pair in representatives:
        if block_count >= target:
            break
        if any(coordinate in white_constraints for coordinate in pair):
            continue
        if all(blocks[row][col] for row, col in pair):
            continue
        if block_count + len(pair) > target:
            continue
        _set_pair(blocks, pair, True)
        if _is_valid_partial(blocks):
            block_count += len(pair)
        else:
            _set_pair(blocks, pair, False)

    if block_count != target or validate_layout(blocks):
        return None
    return blocks


def _repair_short_slots(
    blocks: BlockGrid,
    required_white: set[Coordinate],
) -> bool:
    """Block forced one- and two-cell fragments created by constraints."""
    rows = len(blocks)
    cols = len(blocks[0])
    while True:
        forced: set[Coordinate] = set()
        for row in range(rows):
            start = 0
            while start < cols:
                while start < cols and blocks[row][start]:
                    start += 1
                end = start
                while end < cols and not blocks[row][end]:
                    end += 1
                if 0 < end - start < 3:
                    forced.update((row, col) for col in range(start, end))
                start = end
        for col in range(cols):
            start = 0
            while start < rows:
                while start < rows and blocks[start][col]:
                    start += 1
                end = start
                while end < rows and not blocks[end][col]:
                    end += 1
                if 0 < end - start < 3:
                    forced.update((row, col) for row in range(start, end))
                start = end
        if not forced:
            return True
        expanded = set(forced)
        expanded.update((rows - 1 - row, cols - 1 - col) for row, col in forced)
        if expanded & required_white:
            return False
        changed = False
        for row, col in expanded:
            if not blocks[row][col]:
                blocks[row][col] = True
                changed = True
        if not changed:
            return False


def _symmetric_coordinates(
    rows: int,
    cols: int,
    coordinates: Sequence[Coordinate],
) -> set[Coordinate]:
    expanded: set[Coordinate] = set()
    for row, col in coordinates:
        if not (0 <= row < rows and 0 <= col < cols):
            raise ValueError(f"Layout constraint ({row}, {col}) is outside the grid")
        expanded.add((row, col))
        expanded.add((rows - 1 - row, cols - 1 - col))
    return expanded


def _set_pair(blocks: BlockGrid, pair: Sequence[Coordinate], value: bool) -> None:
    for row, col in pair:
        blocks[row][col] = value


def _is_valid_partial(blocks: Sequence[Sequence[bool]]) -> bool:
    return (
        not _has_short_slots(blocks)
        and _white_cells_are_connected(blocks)
        and not _has_two_by_two_blocks(blocks)
    )


def _has_short_slots(blocks: Sequence[Sequence[bool]]) -> bool:
    rows = len(blocks)
    cols = len(blocks[0])
    lines = list(blocks) + [
        [blocks[row][col] for row in range(rows)] for col in range(cols)
    ]
    for line in lines:
        run_length = 0
        for is_block in [*line, True]:
            if not is_block:
                run_length += 1
                continue
            if 0 < run_length < 3:
                return True
            run_length = 0
    return False


def _white_cells_are_connected(blocks: Sequence[Sequence[bool]]) -> bool:
    rows = len(blocks)
    cols = len(blocks[0])
    white_cells = [
        (row, col)
        for row in range(rows)
        for col in range(cols)
        if not blocks[row][col]
    ]
    if not white_cells:
        return False

    visited = {white_cells[0]}
    queue = deque(visited)
    while queue:
        row, col = queue.popleft()
        for row_delta, col_delta in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (row + row_delta, col + col_delta)
            neighbor_row, neighbor_col = neighbor
            if (
                0 <= neighbor_row < rows
                and 0 <= neighbor_col < cols
                and not blocks[neighbor_row][neighbor_col]
                and neighbor not in visited
            ):
                visited.add(neighbor)
                queue.append(neighbor)
    return len(visited) == len(white_cells)


def _has_two_by_two_blocks(blocks: Sequence[Sequence[bool]]) -> bool:
    return any(
        all(
            blocks[row + row_delta][col + col_delta]
            for row_delta in (0, 1)
            for col_delta in (0, 1)
        )
        for row in range(len(blocks) - 1)
        for col in range(len(blocks[0]) - 1)
    )


def _is_rotationally_symmetric(blocks: Sequence[Sequence[bool]]) -> bool:
    rows = len(blocks)
    cols = len(blocks[0])
    return all(
        blocks[row][col] == blocks[rows - 1 - row][cols - 1 - col]
        for row in range(rows)
        for col in range(cols)
    )


def _aesthetic_score(blocks: Sequence[Sequence[bool]]) -> float:
    """Prefer distributed blocks, modest clusters, and fewer very long slots."""
    rows = len(blocks)
    cols = len(blocks[0])
    row_counts = [sum(row) for row in blocks]
    col_counts = [sum(blocks[row][col] for row in range(rows)) for col in range(cols)]
    empty_lines = sum(count == 0 for count in [*row_counts, *col_counts])

    isolated_blocks = 0
    adjacent_pairs = 0
    for row in range(rows):
        for col in range(cols):
            if not blocks[row][col]:
                continue
            neighbors = sum(
                0 <= row + row_delta < rows
                and 0 <= col + col_delta < cols
                and blocks[row + row_delta][col + col_delta]
                for row_delta, col_delta in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
            if neighbors == 0:
                isolated_blocks += 1
            adjacent_pairs += neighbors

    long_slot_penalty = 0
    lines = list(blocks) + [
        [blocks[row][col] for row in range(rows)] for col in range(cols)
    ]
    for line in lines:
        run_length = 0
        for is_block in [*line, True]:
            if not is_block:
                run_length += 1
            else:
                long_slot_penalty += max(0, run_length - 10)
                run_length = 0

    return (
        -12.0 * empty_lines
        - 1.5 * isolated_blocks
        - 0.35 * long_slot_penalty
        + 0.18 * (adjacent_pairs / 2)
    )
