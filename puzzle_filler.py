"""Constraint-programming crossword fill engine."""

from __future__ import annotations

import math
import random
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Deque, Dict, Iterable, List, Mapping, Optional, Set, Tuple, Union

from entry import Entry
from puzzle import Puzzle
from word_filler import WordFiller


class FillStatus(Enum):
    SOLVED = "solved"
    UNSAT = "unsatisfiable"
    TIMEOUT = "timeout"


QUALITY_MODE_CUTOFFS: Mapping[str, Tuple[Optional[float], ...]] = {
    "balanced": (50.0, 40.0, None),
    "strict": (50.0,),
    "open": (None,),
}


@dataclass(frozen=True)
class SolverConfig:
    """Search limits and deterministic value-ordering controls."""

    timeout_seconds: float = 30.0
    max_nodes_per_restart: int = 50_000
    restarts: int = 4
    random_seed: int = 0
    quality_weight: float = 1.0
    quality_cutoffs: Tuple[Optional[float], ...] = (50.0, 40.0, None)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_nodes_per_restart < 0:
            raise ValueError("max_nodes_per_restart cannot be negative")
        if self.restarts < 1:
            raise ValueError("restarts must be at least 1")
        if not self.quality_cutoffs:
            raise ValueError("quality_cutoffs cannot be empty")
        if any(
            cutoff is not None and cutoff < 0 for cutoff in self.quality_cutoffs
        ):
            raise ValueError("quality cutoffs cannot be negative")
        if None in self.quality_cutoffs[:-1]:
            raise ValueError("an unrestricted quality tier must be last")
        numeric_cutoffs = [
            cutoff for cutoff in self.quality_cutoffs if cutoff is not None
        ]
        if numeric_cutoffs != sorted(numeric_cutoffs, reverse=True):
            raise ValueError("quality cutoffs must be ordered from highest to lowest")


@dataclass(frozen=True)
class FillResult:
    status: FillStatus
    assignments: Mapping[str, str]
    nodes: int
    backtracks: int
    backjumps: int
    propagations: int
    attempts: int
    elapsed_seconds: float
    message: str = ""
    minimum_score: Optional[float] = None

    @property
    def solved(self) -> bool:
        return self.status is FillStatus.SOLVED


@dataclass(frozen=True)
class FillAnalysis:
    viable: bool
    score: float
    minimum_domain: int
    average_domain: float
    domain_counts: Mapping[str, int]
    tight_entries: Tuple[Tuple[str, str, int], ...]
    message: str = ""


@dataclass(frozen=True)
class Crossing:
    other_slot: str
    position: int
    other_position: int


@dataclass
class _SearchStats:
    nodes: int = 0
    backtracks: int = 0
    backjumps: int = 0
    propagations: int = 0


@dataclass
class _SearchOutcome:
    solution: Optional[Dict[str, int]] = None
    conflict: Set[str] = field(default_factory=set)
    cutoff: bool = False


@dataclass
class _TierOutcome:
    status: FillStatus
    attempts: int
    solution: Optional[Dict[str, int]] = None
    message: str = ""


class PuzzleFiller:
    """Fills a fixed crossword layout using bitset-backed CSP search.

    Search state lives entirely in candidate domains.  The supplied ``Puzzle``
    is mutated only after a complete assignment passes all constraints.
    """

    def __init__(
        self,
        words_file: Optional[Union[str, Path]] = None,
        *,
        word_filler: Optional[WordFiller] = None,
        word_scores: Optional[Mapping[str, float]] = None,
        scores_file: Optional[Union[str, Path]] = None,
        config: Optional[SolverConfig] = None,
    ) -> None:
        if word_filler is not None and any(
            option is not None for option in (words_file, word_scores, scores_file)
        ):
            raise ValueError(
                "word_filler cannot be combined with word or score file options"
            )
        self.word_filler = word_filler or WordFiller(
            words_file, word_scores=word_scores, scores_file=scores_file
        )
        self.config = config or SolverConfig()

        self._entries: Dict[str, Entry] = {}
        self._all_entries: Dict[str, Entry] = {}
        self._fixed_answers: Dict[str, str] = {}
        self._lengths: Dict[str, int] = {}
        self._crossings: Dict[str, Tuple[Crossing, ...]] = {}
        self._all_crossings: Dict[str, Tuple[Crossing, ...]] = {}
        self._slots_by_length: Dict[int, Tuple[str, ...]] = {}
        self._all_arcs: Tuple[Tuple[str, Crossing], ...] = ()
        self._deadline = 0.0
        self._attempt_nodes = 0
        self._stats = _SearchStats()

    def fill_puzzle(
        self,
        puzzle: Puzzle,
        config: Optional[SolverConfig] = None,
    ) -> FillResult:
        """Fill ``puzzle`` or report that it is unsatisfiable/timed out."""
        active_config = config or self.config
        started_at = time.perf_counter()
        overall_deadline = started_at + active_config.timeout_seconds
        self._stats = _SearchStats()
        self._prepare_structure(puzzle)
        attempts = 0
        last_outcome: Optional[_TierOutcome] = None
        tiers = active_config.quality_cutoffs

        for tier_index, minimum_score in enumerate(tiers):
            now = time.perf_counter()
            if now >= overall_deadline:
                break
            remaining_tiers = len(tiers) - tier_index
            self._deadline = (
                overall_deadline
                if remaining_tiers == 1
                else now + (overall_deadline - now) / remaining_tiers
            )
            tier_outcome = self._fill_quality_tier(
                active_config,
                minimum_score,
                seed_offset=tier_index * active_config.restarts,
            )
            attempts += tier_outcome.attempts
            last_outcome = tier_outcome

            if tier_outcome.solution is not None:
                assignments = {
                    **self._fixed_answers,
                    **self._decode_solution(tier_outcome.solution),
                }
                self._validate_solution(assignments)
                self._apply_solution(assignments)
                return self._result(
                    FillStatus.SOLVED,
                    assignments,
                    attempts,
                    started_at,
                    self._quality_tier_message(minimum_score, tier_index),
                    minimum_score=minimum_score,
                )

        if time.perf_counter() >= overall_deadline or (
            last_outcome is not None and last_outcome.status is FillStatus.TIMEOUT
        ):
            return self._result(
                FillStatus.TIMEOUT,
                {},
                attempts,
                started_at,
                "Search budget exhausted; the puzzle was left unchanged",
            )

        message = (
            last_outcome.message
            if len(tiers) == 1 and last_outcome is not None
            else "No valid fill was found after trying every quality tier"
        )
        return self._result(
            FillStatus.UNSAT,
            {},
            attempts,
            started_at,
            message,
        )

    def analyze_puzzle(
        self,
        puzzle: Puzzle,
        *,
        minimum_score: Optional[float] = None,
    ) -> FillAnalysis:
        """Run domain construction and arc consistency without search."""
        self._stats = _SearchStats()
        self._prepare_structure(puzzle)
        duplicate_fixed = len(set(self._fixed_answers.values())) != len(
            self._fixed_answers
        )
        if duplicate_fixed:
            return FillAnalysis(
                viable=False,
                score=0.0,
                minimum_domain=0,
                average_domain=0.0,
                domain_counts={},
                tight_entries=(),
                message="Required answers contain a duplicate",
            )

        domains = {
            slot: self.word_filler.domain_for_pattern(
                entry.get_current_hint(), minimum_score=minimum_score
            )
            for slot, entry in self._entries.items()
        }
        self._remove_fixed_answers(domains)
        empty_slots = [slot for slot, domain in domains.items() if domain == 0]
        if empty_slots:
            counts = {slot: domain.bit_count() for slot, domain in domains.items()}
            tight = self._tight_entry_summary(counts)
            return FillAnalysis(
                viable=False,
                score=0.0,
                minimum_domain=0,
                average_domain=0.0,
                domain_counts=counts,
                tight_entries=tight,
                message=f"No dictionary candidates for: {', '.join(sorted(empty_slots))}",
            )

        reasons = {slot: {slot} for slot in domains}
        conflict = self._propagate(domains, reasons)
        counts = {slot: domain.bit_count() for slot, domain in domains.items()}
        tight = self._tight_entry_summary(counts)
        if conflict is not None:
            involved = ", ".join(sorted(conflict))
            return FillAnalysis(
                viable=False,
                score=0.0,
                minimum_domain=min(counts.values(), default=0),
                average_domain=0.0,
                domain_counts=counts,
                tight_entries=tight,
                message=(
                    f"Crossing constraints conflict near {involved}"
                    if involved
                    else "Crossing constraints are inconsistent"
                ),
            )

        if not counts:
            return FillAnalysis(
                viable=True,
                score=100.0,
                minimum_domain=1,
                average_domain=1.0,
                domain_counts=counts,
                tight_entries=tight,
                message="All entries are already fixed",
            )
        log_counts = [math.log1p(count) for count in counts.values()]
        average_domain = math.expm1(sum(log_counts) / len(log_counts))
        minimum_domain = min(counts.values())
        score = sum(log_counts) / len(log_counts) + 0.5 * math.log1p(minimum_domain)
        return FillAnalysis(
            viable=True,
            score=score,
            minimum_domain=minimum_domain,
            average_domain=average_domain,
            domain_counts=counts,
            tight_entries=tight,
            message="All entries retain dictionary support after propagation",
        )

    def _tight_entry_summary(
        self,
        counts: Mapping[str, int],
    ) -> Tuple[Tuple[str, str, int], ...]:
        ordered = sorted(counts, key=lambda slot: (counts[slot], slot))[:6]
        return tuple(
            (slot, self._entries[slot].get_current_hint(), counts[slot])
            for slot in ordered
        )

    def _fill_quality_tier(
        self,
        config: SolverConfig,
        minimum_score: Optional[float],
        *,
        seed_offset: int,
    ) -> _TierOutcome:
        domains = {}
        for slot, entry in self._entries.items():
            pattern = entry.get_current_hint()
            # A complete answer represents an explicit user lock/theme answer and is
            # preserved even when its editorial score is below this tier.
            score_floor = minimum_score if "." in pattern else None
            domains[slot] = self.word_filler.domain_for_pattern(
                pattern,
                minimum_score=score_floor,
            )
        self._remove_fixed_answers(domains)

        empty_slots = [slot for slot, domain in domains.items() if domain == 0]
        if empty_slots:
            return _TierOutcome(
                FillStatus.UNSAT,
                0,
                message=f"No dictionary candidates for: {', '.join(sorted(empty_slots))}",
            )

        reasons = {slot: set() for slot in domains}
        initial_conflict = self._propagate(domains, reasons)
        if initial_conflict is not None:
            return _TierOutcome(
                FillStatus.UNSAT,
                0,
                message="Initial letters and crossword constraints are inconsistent",
            )

        attempts = 0
        for attempt in range(config.restarts):
            if time.perf_counter() >= self._deadline:
                break
            attempts = attempt + 1
            self._attempt_nodes = 0
            rng = random.Random(config.random_seed + seed_offset + attempt)
            attempt_domains = domains.copy()
            attempt_reasons = {slot: set(reason) for slot, reason in reasons.items()}
            outcome = self._search(
                attempt_domains,
                attempt_reasons,
                rng,
                config,
            )
            if outcome.solution is not None:
                return _TierOutcome(
                    FillStatus.SOLVED,
                    attempts,
                    solution=outcome.solution,
                )
            if not outcome.cutoff:
                return _TierOutcome(
                    FillStatus.UNSAT,
                    attempts,
                    message="The search space was exhausted without a valid fill",
                )

        return _TierOutcome(
            FillStatus.TIMEOUT,
            attempts,
            message="This quality tier exhausted its search budget",
        )

    def _remove_fixed_answers(self, domains: Dict[str, int]) -> None:
        for answer in set(self._fixed_answers.values()):
            word_id = self.word_filler.word_id(answer)
            if word_id is None:
                continue
            word_bit = 1 << word_id
            for slot in self._slots_by_length.get(len(answer), ()):
                domains[slot] &= ~word_bit

    @staticmethod
    def _quality_tier_message(
        minimum_score: Optional[float],
        tier_index: int,
    ) -> str:
        if minimum_score is None:
            return "Solved after allowing the full quality-ranked word list"
        score = f"{minimum_score:g}+"
        if tier_index == 0:
            return f"Solved with a {score} minimum for replaceable entries"
        return f"Solved after relaxing replaceable entries to a {score} minimum"

    # Compatibility entry points now use the sound CSP solver.
    def fill_puzzle_using_backtracking(self, puzzle: Puzzle) -> FillResult:
        return self.fill_puzzle(puzzle)

    def fill_puzzle_using_heuristic(self, puzzle: Puzzle) -> FillResult:
        return self.fill_puzzle(puzzle)

    def _prepare_structure(self, puzzle: Puzzle) -> None:
        if not hasattr(puzzle, "entries"):
            raise ValueError("Puzzle.initialize() must be called before filling")

        self._all_entries = dict(puzzle.entries)
        self._fixed_answers = {
            slot: entry.get_current_hint()
            for slot, entry in self._all_entries.items()
            if "." not in entry.get_current_hint()
        }
        self._entries = {
            slot: entry
            for slot, entry in self._all_entries.items()
            if slot not in self._fixed_answers
        }
        self._lengths = {
            slot: entry.answer_length for slot, entry in self._entries.items()
        }

        square_locations: Dict[int, List[Tuple[str, int]]] = defaultdict(list)
        for slot, entry in self._all_entries.items():
            for position, square in enumerate(entry.squares):
                square_locations[id(square)].append((slot, position))

        all_crossings: Dict[str, List[Crossing]] = {
            slot: [] for slot in self._all_entries
        }
        for locations in square_locations.values():
            if len(locations) != 2:
                continue
            (first_slot, first_position), (second_slot, second_position) = locations
            all_crossings[first_slot].append(
                Crossing(second_slot, first_position, second_position)
            )
            all_crossings[second_slot].append(
                Crossing(first_slot, second_position, first_position)
            )

        self._all_crossings = {
            slot: tuple(slot_crossings)
            for slot, slot_crossings in all_crossings.items()
        }
        self._crossings = {
            slot: tuple(
                crossing
                for crossing in all_crossings[slot]
                if crossing.other_slot in self._entries
            )
            for slot in self._entries
        }
        slots_by_length: Dict[int, List[str]] = defaultdict(list)
        for slot, length in self._lengths.items():
            slots_by_length[length].append(slot)
        self._slots_by_length = {
            length: tuple(slots) for length, slots in slots_by_length.items()
        }
        self._all_arcs = tuple(
            (slot, crossing)
            for slot, slot_crossings in self._crossings.items()
            for crossing in slot_crossings
        )

    def _propagate(
        self,
        domains: Dict[str, int],
        reasons: Dict[str, Set[str]],
    ) -> Optional[Set[str]]:
        """Maintain crossing arc consistency and singleton all-different."""
        arc_queue: Deque[Tuple[str, Crossing]] = deque(self._all_arcs)
        singleton_queue: Deque[str] = deque(
            slot for slot, domain in domains.items() if domain.bit_count() == 1
        )
        processed_singletons: Set[Tuple[str, int]] = set()

        while arc_queue or singleton_queue:
            while singleton_queue:
                source_slot = singleton_queue.popleft()
                source_domain = domains[source_slot]
                if source_domain.bit_count() != 1:
                    continue
                singleton_key = (source_slot, source_domain)
                if singleton_key in processed_singletons:
                    continue
                processed_singletons.add(singleton_key)

                for target_slot in self._slots_by_length[self._lengths[source_slot]]:
                    if target_slot == source_slot or not (
                        domains[target_slot] & source_domain
                    ):
                        continue
                    new_domain = domains[target_slot] & ~source_domain
                    reasons[target_slot].update(reasons[source_slot])
                    self._stats.propagations += 1
                    if new_domain == 0:
                        return set(reasons[target_slot])
                    domains[target_slot] = new_domain
                    if new_domain.bit_count() == 1:
                        singleton_queue.append(target_slot)
                    self._queue_dependents(target_slot, arc_queue)

            if not arc_queue:
                continue
            target_slot, crossing = arc_queue.popleft()
            source_slot = crossing.other_slot
            target_domain = domains[target_slot]
            source_domain = domains[source_slot]

            allowed_target_values = 0
            source_length = self._lengths[source_slot]
            target_length = self._lengths[target_slot]
            for letter_index in self.word_filler.supported_letters(
                source_length,
                crossing.other_position,
                source_domain,
            ):
                allowed_target_values |= self.word_filler.position_masks[target_length][
                    crossing.position
                ][letter_index]

            new_domain = target_domain & allowed_target_values
            if new_domain == target_domain:
                continue

            reasons[target_slot].update(reasons[source_slot])
            self._stats.propagations += 1
            if new_domain == 0:
                return set(reasons[target_slot])
            domains[target_slot] = new_domain
            if new_domain.bit_count() == 1:
                singleton_queue.append(target_slot)
            self._queue_dependents(target_slot, arc_queue)

        return None

    def _queue_dependents(
        self,
        changed_slot: str,
        arc_queue: Deque[Tuple[str, Crossing]],
    ) -> None:
        for crossing in self._crossings[changed_slot]:
            reverse_crossing = Crossing(
                other_slot=changed_slot,
                position=crossing.other_position,
                other_position=crossing.position,
            )
            arc_queue.append((crossing.other_slot, reverse_crossing))

    def _search(
        self,
        domains: Dict[str, int],
        reasons: Dict[str, Set[str]],
        rng: random.Random,
        config: SolverConfig,
    ) -> _SearchOutcome:
        slot = self._select_slot(domains)
        if slot is None:
            return _SearchOutcome(solution=domains)

        if (
            time.perf_counter() >= self._deadline
            or self._attempt_nodes >= config.max_nodes_per_restart
        ):
            return _SearchOutcome(cutoff=True)

        self._attempt_nodes += 1
        self._stats.nodes += 1
        accumulated_conflicts: Set[str] = set(reasons[slot])

        for word_id in self._ordered_word_ids(slot, domains, rng, config):
            if time.perf_counter() >= self._deadline:
                return _SearchOutcome(cutoff=True)
            child_domains = domains.copy()
            child_reasons = {
                child_slot: set(reason) for child_slot, reason in reasons.items()
            }
            child_domains[slot] = 1 << word_id
            child_reasons[slot].add(slot)

            conflict = self._propagate(child_domains, child_reasons)
            if conflict is None:
                outcome = self._search(child_domains, child_reasons, rng, config)
            else:
                outcome = _SearchOutcome(conflict=conflict)

            if outcome.solution is not None or outcome.cutoff:
                return outcome

            if slot not in outcome.conflict:
                self._stats.backjumps += 1
                return outcome
            accumulated_conflicts.update(outcome.conflict - {slot})

        self._stats.backtracks += 1
        return _SearchOutcome(conflict=accumulated_conflicts)

    def _select_slot(self, domains: Mapping[str, int]) -> Optional[str]:
        unassigned = [
            slot for slot, domain in domains.items() if domain.bit_count() > 1
        ]
        if not unassigned:
            return None

        def ordering_key(slot: str) -> Tuple[int, int, int, str]:
            unassigned_neighbors = sum(
                domains[crossing.other_slot].bit_count() > 1
                for crossing in self._crossings[slot]
            )
            return (
                domains[slot].bit_count(),
                -unassigned_neighbors,
                -self._lengths[slot],
                slot,
            )

        return min(unassigned, key=ordering_key)

    def _ordered_word_ids(
        self,
        slot: str,
        domains: Mapping[str, int],
        rng: random.Random,
        config: SolverConfig,
    ) -> Iterable[int]:
        length = self._lengths[slot]
        same_length_slots = self._slots_by_length[length]
        scored_values = []

        for word_id in self.word_filler.iter_word_ids(domains[slot]):
            word = self.word_filler.word_for_id(length, word_id)
            least_constraining_score = 0.0
            for crossing in self._crossings[slot]:
                other_slot = crossing.other_slot
                other_length = self._lengths[other_slot]
                letter = word[crossing.position]
                support_count = (
                    domains[other_slot]
                    & self.word_filler.mask_for_letter(
                        other_length,
                        crossing.other_position,
                        letter,
                    )
                ).bit_count()
                least_constraining_score += math.log1p(support_count)

            word_bit = 1 << word_id
            duplicate_pressure = sum(
                bool(domains[other_slot] & word_bit)
                for other_slot in same_length_slots
                if other_slot != slot
            )
            quality_score = self.word_filler.quality_score(length, word_id)
            combined_score = (
                least_constraining_score
                - math.log1p(duplicate_pressure)
                + config.quality_weight * quality_score
            )
            scored_values.append((combined_score, quality_score, rng.random(), word_id))

        scored_values.sort(reverse=True)
        return (word_id for _, _, _, word_id in scored_values)

    def _decode_solution(self, domains: Mapping[str, int]) -> Dict[str, str]:
        assignments: Dict[str, str] = {}
        for slot, domain in domains.items():
            if domain.bit_count() != 1:
                raise RuntimeError(
                    f"Internal solver error: non-singleton terminal domain for {slot}"
                )
            word_id = domain.bit_length() - 1
            assignments[slot] = self.word_filler.word_for_id(
                self._lengths[slot], word_id
            )
        return assignments

    def _validate_solution(self, assignments: Mapping[str, str]) -> None:
        if set(assignments) != set(self._all_entries):
            raise RuntimeError("Internal solver error: solution is missing entries")
        if len(set(assignments.values())) != len(assignments):
            raise RuntimeError(
                "Internal solver error: solution contains duplicate answers"
            )

        for slot, word in assignments.items():
            entry = self._all_entries[slot]
            pattern = entry.get_current_hint()
            if len(word) != len(pattern) or any(
                expected != "." and expected != actual
                for expected, actual in zip(pattern, word)
            ):
                raise RuntimeError(
                    f"Internal solver error: {word} conflicts with {slot} ({pattern})"
                )
            for crossing in self._all_crossings[slot]:
                if (
                    word[crossing.position]
                    != assignments[crossing.other_slot][crossing.other_position]
                ):
                    raise RuntimeError(
                        f"Internal solver error: crossing mismatch at {slot}"
                    )

    def _apply_solution(self, assignments: Mapping[str, str]) -> None:
        for slot, word in assignments.items():
            entry = self._all_entries[slot]
            for square, letter in zip(entry.squares, word):
                square.letter = letter
            if entry.clue is None or entry.clue.startswith("Clue for "):
                entry.clue = "Clue for " + word

    def _result(
        self,
        status: FillStatus,
        assignments: Mapping[str, str],
        attempts: int,
        started_at: float,
        message: str = "",
        *,
        minimum_score: Optional[float] = None,
    ) -> FillResult:
        return FillResult(
            status=status,
            assignments=dict(assignments),
            nodes=self._stats.nodes,
            backtracks=self._stats.backtracks,
            backjumps=self._stats.backjumps,
            propagations=self._stats.propagations,
            attempts=attempts,
            elapsed_seconds=time.perf_counter() - started_at,
            message=message,
            minimum_score=minimum_score,
        )
