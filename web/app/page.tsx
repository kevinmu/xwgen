"use client";

import {
  ChangeEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

type Direction = "A" | "D";
type LayoutProfile = "airy" | "classic" | "dense";
type QualityMode = "balanced" | "strict" | "open";
type ThemeCount = 4 | 5 | 6;

type Cell = {
  black: boolean;
  letter: string;
  locked: boolean;
  number?: number | null;
};

type Entry = {
  id: string;
  number: number;
  direction: Direction;
  row: number;
  col: number;
  length: number;
  cells: Array<[number, number]>;
  pattern: string;
};

type SerializedEntry = {
  id: string;
  clue: string;
  answer?: string;
  pattern?: string;
  score?: number | null;
};

type EntryScore = {
  word: string;
  score: number | null;
};

type PuzzlePayload = {
  rows: number;
  cols: number;
  title: string;
  author: string;
  copyright: string;
  note: string;
  cells: Cell[][];
  entries?: SerializedEntry[];
  warnings?: string[];
  result?: FillStats;
  layout?: {
    profile: LayoutProfile;
    blockCount: number;
    targetBlockCount: number;
    density: number;
    seed: number;
    currentLayout?: boolean;
  };
};

type FillStats = {
  status: string;
  message: string;
  nodes: number;
  backtracks: number;
  backjumps: number;
  propagations: number;
  attempts: number;
  elapsedSeconds: number;
  minimumScore: number | null;
  qualityMode: QualityMode;
};

type LexiconMetadata = {
  source: string;
  scored: boolean;
  entries: number;
  license: string;
};

type CandidateResponse = {
  entryId: string;
  pattern: string;
  total: number;
  candidates: Array<{ word: string; score: number }>;
  selectedWord: {
    word: string;
    score: number | null;
    inLexicon: boolean;
  } | null;
  lexicon: LexiconMetadata;
};

type ThemeAnswerDraft = {
  answer: string;
};

type ThemePlacement = {
  answerIndex: number;
  answer: string;
  entryId: string;
  row: number;
  col: number;
  length: number;
  label: "Flexible" | "Constrained" | "Tight" | "Blocked";
  minimumCrossingDomain: number;
  crossingCount: number;
};

type ThemeLayoutCandidate = PuzzlePayload & {
  id: string;
  layout: NonNullable<PuzzlePayload["layout"]>;
  placements: ThemePlacement[];
  analysis: {
    verification: "verified" | "promising" | "preflight" | "blocked";
    rating: string;
    viable: boolean;
    score: number;
    minimumDomain: number;
    averageDomain: number;
    message: string;
    tightEntries: Array<{ id: string; pattern: string; candidates: number }>;
  };
};

type ThemeLayoutsResponse = {
  answers: string[];
  candidates: ThemeLayoutCandidate[];
  message: string;
  error?: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_XWGEN_API ?? "http://127.0.0.1:8765/api";

const cloneGrid = (cells: Cell[][]): Cell[][] =>
  cells.map((row) => row.map((cell) => ({ ...cell })));

const entryScoresFrom = (entries?: SerializedEntry[]): Record<string, EntryScore> =>
  Object.fromEntries(
    (entries ?? [])
      .filter((entry) => entry.pattern && !entry.pattern.includes("."))
      .map((entry) => [
        entry.id,
        { word: entry.pattern as string, score: entry.score ?? null },
      ]),
  );

const qualityLetterColor = (score: number): string => {
  const normalized = Math.max(0, Math.min(70, score)) / 70;
  const saturation = 76 - normalized * 56;
  const lightness = 42 - normalized * 25;
  return `hsl(4 ${saturation}% ${lightness}%)`;
};

const blankGrid = (rows = 15, cols = 15): Cell[][] =>
  Array.from({ length: rows }, () =>
    Array.from({ length: cols }, () => ({
      black: false,
      letter: "",
      locked: false,
    })),
  );

function deriveEntries(cells: Cell[][]): { cells: Cell[][]; entries: Entry[] } {
  const numbered = cloneGrid(cells);
  const entries: Entry[] = [];
  let nextNumber = 0;
  const rows = cells.length;
  const cols = cells[0]?.length ?? 0;

  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      if (cells[row][col].black) {
        numbered[row][col].number = null;
        continue;
      }
      const startsAcross = col === 0 || cells[row][col - 1].black;
      const startsDown = row === 0 || cells[row - 1][col].black;
      if (!startsAcross && !startsDown) {
        numbered[row][col].number = null;
        continue;
      }
      nextNumber += 1;
      numbered[row][col].number = nextNumber;

      if (startsAcross) {
        const entryCells: Array<[number, number]> = [];
        for (let cursor = col; cursor < cols && !cells[row][cursor].black; cursor += 1) {
          entryCells.push([row, cursor]);
        }
        entries.push(makeEntry(nextNumber, "A", row, col, entryCells, cells));
      }
      if (startsDown) {
        const entryCells: Array<[number, number]> = [];
        for (let cursor = row; cursor < rows && !cells[cursor][col].black; cursor += 1) {
          entryCells.push([cursor, col]);
        }
        entries.push(makeEntry(nextNumber, "D", row, col, entryCells, cells));
      }
    }
  }
  return { cells: numbered, entries };
}

function makeEntry(
  number: number,
  direction: Direction,
  row: number,
  col: number,
  entryCells: Array<[number, number]>,
  cells: Cell[][],
): Entry {
  return {
    id: `${number}${direction}`,
    number,
    direction,
    row,
    col,
    length: entryCells.length,
    cells: entryCells,
    pattern: entryCells.map(([r, c]) => cells[r][c].letter || ".").join(""),
  };
}

const normalizeThemeAnswer = (value: string): string =>
  value.toUpperCase().replace(/[^A-Z]/g, "");

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function parseAscii(contents: string): PuzzlePayload & { clues: Record<string, string> } {
  const lines = contents.replace(/\r/g, "").split("\n");
  const rows = Number(lines[0]);
  const cols = Number(lines[1]);
  if (!Number.isInteger(rows) || !Number.isInteger(cols) || rows < 3 || cols < 3) {
    throw new Error("That file does not begin with valid grid dimensions.");
  }
  const gridLines = lines.slice(6, 6 + rows);
  if (gridLines.length !== rows || gridLines.some((line) => line.length !== cols)) {
    throw new Error("The grid dimensions do not match the file contents.");
  }
  const clues: Record<string, string> = {};
  for (const line of lines.slice(6 + rows)) {
    const match = line.match(/^(\d+[AD]):\s*(.*?)\s*(?:\([^)]*\))?$/);
    if (match) clues[match[1]] = match[2];
  }
  return {
    rows,
    cols,
    title: lines[2] ?? "Untitled crossword",
    author: lines[3] ?? "",
    copyright: lines[4] ?? "",
    note: lines[5] ?? "",
    cells: gridLines.map((line) =>
      [...line].map((value) => ({
        black: value === "*",
        letter: value === "*" || value === "-" ? "" : value.toUpperCase(),
        locked: value !== "*" && value !== "-",
      })),
    ),
    clues,
  };
}

export default function Home() {
  const [grid, setGrid] = useState<Cell[][]>(() => blankGrid());
  const [metadata, setMetadata] = useState({
    title: "Untitled crossword",
    author: "",
    copyright: "",
    note: "",
  });
  const [clues, setClues] = useState<Record<string, string>>({});
  const [entryScores, setEntryScores] = useState<Record<string, EntryScore>>({});
  const [selected, setSelected] = useState<[number, number]>([0, 0]);
  const [direction, setDirection] = useState<Direction>("A");
  const [tool, setTool] = useState<"type" | "block">("type");
  const [symmetry, setSymmetry] = useState(true);
  const [engine, setEngine] = useState<"checking" | "ready" | "offline">("checking");
  const [busy, setBusy] = useState(false);
  const [layoutBusy, setLayoutBusy] = useState(false);
  const [layoutProfile, setLayoutProfile] = useState<LayoutProfile>("classic");
  const [qualityMode, setQualityMode] = useState<QualityMode>("balanced");
  const [candidateData, setCandidateData] = useState<CandidateResponse | null>(null);
  const [lexicon, setLexicon] = useState<LexiconMetadata | null>(null);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [past, setPast] = useState<Cell[][][]>([]);
  const [future, setFuture] = useState<Cell[][][]>([]);
  const [themeWizardOpen, setThemeWizardOpen] = useState(false);
  const [themeStep, setThemeStep] = useState<1 | 2 | 3>(1);
  const [themeCount, setThemeCount] = useState<ThemeCount>(4);
  const [themeName, setThemeName] = useState("");
  const [themeDrafts, setThemeDrafts] = useState<ThemeAnswerDraft[]>([]);
  const [themeLayouts, setThemeLayouts] = useState<ThemeLayoutCandidate[]>([]);
  const [selectedThemeLayoutId, setSelectedThemeLayoutId] = useState("");
  const [themeSearching, setThemeSearching] = useState(false);
  const [themeError, setThemeError] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const layoutSeedRef = useRef(0);
  const themeSeedRef = useRef(0);

  const derived = useMemo(() => deriveEntries(grid), [grid]);
  const numberedGrid = derived.cells;
  const entries = derived.entries;
  const cellQuality = useMemo(() => {
    const quality = new Map<string, { score: number; entries: string[] }>();

    entries.forEach((entry) => {
      const saved = entryScores[entry.id];
      if (
        !saved ||
        saved.score === null ||
        entry.pattern.includes(".") ||
        saved.word !== entry.pattern
      ) {
        return;
      }
      const score = saved.score;

      entry.cells.forEach(([row, col]) => {
        const key = `${row}:${col}`;
        const current = quality.get(key);
        if (!current || score < current.score) {
          quality.set(key, { score, entries: [entry.id] });
        } else if (score === current.score) {
          current.entries.push(entry.id);
        }
      });
    });

    return quality;
  }, [entries, entryScores]);

  const entriesAtSelection = useMemo(
    () =>
      entries.filter((entry) =>
        entry.cells.some(([row, col]) => row === selected[0] && col === selected[1]),
      ),
    [entries, selected],
  );

  const activeEntry = useMemo(
    () =>
      entriesAtSelection.find((entry) => entry.direction === direction) ??
      entriesAtSelection[0] ??
      null,
    [direction, entriesAtSelection],
  );

  const acrossEntries = entries.filter((entry) => entry.direction === "A");
  const downEntries = entries.filter((entry) => entry.direction === "D");
  const missingClueCount = entries.filter((entry) => !clues[entry.id]?.trim()).length;
  const activeCandidateData =
    candidateData?.entryId === activeEntry?.id ? candidateData : null;
  const selectedThemeLayout =
    themeLayouts.find((candidate) => candidate.id === selectedThemeLayoutId) ?? null;

  const buildPayload = useCallback(
    () => ({
      rows: grid.length,
      cols: grid[0]?.length ?? 0,
      ...metadata,
      cells: grid,
      clues,
    }),
    [clues, grid, metadata],
  );

  const loadPuzzle = useCallback((puzzle: PuzzlePayload) => {
    setGrid(puzzle.cells);
    setMetadata({
      title: puzzle.title || "Untitled crossword",
      author: puzzle.author || "",
      copyright: puzzle.copyright || "",
      note: puzzle.note || "",
    });
    if (puzzle.entries) {
      setClues(Object.fromEntries(puzzle.entries.map((entry) => [entry.id, entry.clue])));
    }
    setEntryScores(entryScoresFrom(puzzle.entries));
    setPast([]);
    setFuture([]);
    setSelected([0, 0]);
    setDirection("A");
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function start() {
      try {
        const health = await fetch(`${API_BASE}/health`);
        if (!health.ok) throw new Error("offline");
        const healthData = (await health.json()) as {
          ok: boolean;
          lexicon: LexiconMetadata;
        };
        const response = await fetch(`${API_BASE}/sample`);
        if (!response.ok) throw new Error("sample unavailable");
        const sample = (await response.json()) as PuzzlePayload;
        if (cancelled) return;
        setLexicon(healthData.lexicon);
        setEngine("ready");
        loadPuzzle(sample);
      } catch {
        if (cancelled) return;
        setEngine("offline");
      }
    }
    void start();
    return () => {
      cancelled = true;
    };
  }, [loadPuzzle]);

  useEffect(() => {
    if (engine !== "ready" || !activeEntry || activeEntry.length < 1) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setCandidateLoading(true);
      try {
        const response = await fetch(`${API_BASE}/candidates`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...buildPayload(), entryId: activeEntry.id, limit: 40 }),
        });
        if (!response.ok) throw new Error("candidate lookup failed");
        const data = (await response.json()) as CandidateResponse;
        if (!cancelled) {
          setCandidateData(data);
          const selectedWord = data.selectedWord;
          if (
            !activeEntry.pattern.includes(".") &&
            selectedWord?.word === activeEntry.pattern
          ) {
            const score =
              selectedWord.inLexicon && data.lexicon.scored
                ? selectedWord.score
                : null;
            setEntryScores((current) => ({
              ...current,
              [activeEntry.id]: { word: activeEntry.pattern, score },
            }));
          }
        }
      } catch {
        if (!cancelled) setCandidateData(null);
      } finally {
        if (!cancelled) setCandidateLoading(false);
      }
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeEntry, buildPayload, engine]);

  const commitGrid = useCallback(
    (next: Cell[][]) => {
      setPast((items) => [...items.slice(-49), cloneGrid(grid)]);
      setFuture([]);
      setGrid(next);
    },
    [grid],
  );

  const undo = useCallback(() => {
    const previous = past.at(-1);
    if (!previous) return;
    setFuture((items) => [cloneGrid(grid), ...items.slice(0, 49)]);
    setGrid(previous);
    setPast((items) => items.slice(0, -1));
  }, [grid, past]);

  const redo = useCallback(() => {
    const next = future[0];
    if (!next) return;
    setPast((items) => [...items.slice(-49), cloneGrid(grid)]);
    setGrid(next);
    setFuture((items) => items.slice(1));
  }, [future, grid]);

  const selectCell = (row: number, col: number) => {
    if (tool === "block") {
      toggleBlock(row, col);
      return;
    }
    if (grid[row][col].black) return;
    if (selected[0] === row && selected[1] === col && entriesAtSelection.length > 1) {
      setDirection((current) => (current === "A" ? "D" : "A"));
    } else {
      const cellEntries = entries.filter((entry) =>
        entry.cells.some(([r, c]) => r === row && c === col),
      );
      if (!cellEntries.some((entry) => entry.direction === direction)) {
        setDirection(cellEntries[0]?.direction ?? "A");
      }
    }
    setSelected([row, col]);
  };

  const toggleBlock = (row: number, col: number) => {
    const next = cloneGrid(grid);
    const newValue = !next[row][col].black;
    const apply = (targetRow: number, targetCol: number) => {
      next[targetRow][targetCol] = {
        ...next[targetRow][targetCol],
        black: newValue,
        letter: "",
        locked: false,
      };
    };
    apply(row, col);
    if (symmetry) apply(grid.length - 1 - row, grid[0].length - 1 - col);
    commitGrid(next);
  };

  const moveSelection = useCallback(
    (rowDelta: number, colDelta: number) => {
      let row = selected[0];
      let col = selected[1];
      do {
        row = Math.max(0, Math.min(grid.length - 1, row + rowDelta));
        col = Math.max(0, Math.min(grid[0].length - 1, col + colDelta));
        if (!grid[row][col].black) break;
      } while (
        row > 0 && row < grid.length - 1 && col > 0 && col < grid[0].length - 1
      );
      setSelected([row, col]);
    },
    [grid, selected],
  );

  const moveWithinEntry = (offset: number) => {
    if (!activeEntry) return;
    const index = activeEntry.cells.findIndex(
      ([row, col]) => row === selected[0] && col === selected[1],
    );
    const target = activeEntry.cells[Math.max(0, Math.min(activeEntry.length - 1, index + offset))];
    if (target) setSelected(target);
  };

  const handleCellKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.ctrlKey || event.metaKey) {
      if (event.key.toLowerCase() === "z") {
        event.preventDefault();
        if (event.shiftKey) redo();
        else undo();
      }
      return;
    }
    if (/^[a-zA-Z]$/.test(event.key)) {
      event.preventDefault();
      const next = cloneGrid(grid);
      const [row, col] = selected;
      next[row][col] = {
        ...next[row][col],
        letter: event.key.toUpperCase(),
        locked: true,
      };
      commitGrid(next);
      moveWithinEntry(1);
      return;
    }
    if (event.key === "Backspace" || event.key === "Delete") {
      event.preventDefault();
      const [row, col] = selected;
      if (!grid[row][col].letter && event.key === "Backspace") moveWithinEntry(-1);
      const next = cloneGrid(grid);
      next[row][col] = { ...next[row][col], letter: "", locked: false };
      commitGrid(next);
      return;
    }
    const movement: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    if (movement[event.key]) {
      event.preventDefault();
      moveSelection(...movement[event.key]);
    } else if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      setDirection((current) => (current === "A" ? "D" : "A"));
    } else if (event.key === "." || event.key === "#") {
      event.preventDefault();
      toggleBlock(...selected);
    }
  };

  const applyCandidate = (word: string) => {
    if (!activeEntry) return;
    const next = cloneGrid(grid);
    activeEntry.cells.forEach(([row, col], index) => {
      next[row][col] = { ...next[row][col], letter: word[index], locked: true };
    });
    const candidate = activeCandidateData?.candidates.find((item) => item.word === word);
    setEntryScores((current) => ({
      ...current,
      [activeEntry.id]: {
        word,
        score: activeCandidateData?.lexicon.scored ? (candidate?.score ?? null) : null,
      },
    }));
    commitGrid(next);
  };

  const toggleActiveLock = () => {
    if (!activeEntry) return;
    const next = cloneGrid(grid);
    const shouldLock = !activeEntry.cells.every(
      ([row, col]) => !next[row][col].letter || next[row][col].locked,
    );
    activeEntry.cells.forEach(([row, col]) => {
      if (next[row][col].letter) next[row][col].locked = shouldLock;
    });
    commitGrid(next);
  };

  const fillGrid = async (gridOverride?: Cell[][]) => {
    if (engine !== "ready" || busy) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/fill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          ...buildPayload(),
          ...(gridOverride ? { cells: gridOverride, clues: {} } : {}),
          options: {
            timeout: 30,
            nodesPerRestart: 50000,
            restarts: 4,
            seed: 0,
            qualityMode,
          },
        }),
      });
      const data = (await response.json()) as PuzzlePayload & { error?: string };
      if (!response.ok) throw new Error(data.error || "Fill request failed");
      if (data.result?.status === "solved") {
        setEntryScores(entryScoresFrom(data.entries));
        if (gridOverride) {
          setGrid(data.cells);
          setFuture([]);
          setClues(
            Object.fromEntries(
              (data.entries ?? []).map((entry) => [entry.id, entry.clue]),
            ),
          );
        } else {
          commitGrid(data.cells);
          setClues((current) => {
            const next = { ...current };
            data.entries?.forEach((entry) => {
              next[entry.id] = entry.clue;
            });
            return next;
          });
        }
      } else {
        window.alert(data.result?.message || "No valid fill was found.");
      }
    } catch (error) {
      if ((error as Error).name !== "AbortError") window.alert((error as Error).message);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const stopFill = () => abortRef.current?.abort();

  const createThemeDrafts = (count: ThemeCount): ThemeAnswerDraft[] =>
    Array.from({ length: count }, () => ({ answer: "" }));

  const openThemeWizard = () => {
    const currentTitle = metadata.title.trim();
    setThemeName(currentTitle === "Untitled crossword" ? "" : currentTitle);
    setThemeDrafts(createThemeDrafts(themeCount));
    setThemeLayouts([]);
    setSelectedThemeLayoutId("");
    setThemeStep(1);
    setThemeError("");
    setThemeWizardOpen(true);
  };

  const changeThemeCount = (count: ThemeCount) => {
    setThemeCount(count);
    setThemeDrafts((current) =>
      Array.from({ length: count }, (_, index) => current[index] ?? { answer: "" }),
    );
    setThemeLayouts([]);
    setSelectedThemeLayoutId("");
    setThemeError("");
  };

  const validateThemeAnswers = (): boolean => {
    if (themeDrafts.length !== themeCount) {
      setThemeError("Add one answer for every theme slot.");
      return false;
    }
    const maximumLength = grid[0]?.length ?? 15;
    const incomplete = themeDrafts.find(
      ({ answer }) => {
        const length = normalizeThemeAnswer(answer).length;
        return length < 3 || length > maximumLength;
      },
    );
    if (incomplete) {
      setThemeError(
        `Each theme answer needs between 3 and ${maximumLength} letters.`,
      );
      return false;
    }
    const answers = themeDrafts.map(({ answer }) => normalizeThemeAnswer(answer));
    if (new Set(answers).size !== answers.length) {
      setThemeError("Use a different answer for each theme slot.");
      return false;
    }
    setThemeError("");
    return true;
  };

  const findThemeLayouts = async () => {
    if (!validateThemeAnswers() || themeSearching || engine !== "ready") return;
    setThemeStep(2);
    setThemeSearching(true);
    setThemeError("");
    setThemeLayouts([]);
    setSelectedThemeLayoutId("");
    const searchSeed = themeSeedRef.current || Date.now();
    themeSeedRef.current = searchSeed + 1;
    try {
      const response = await fetch(`${API_BASE}/theme-layouts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rows: grid.length,
          cols: grid[0]?.length ?? 0,
          cells: grid,
          title: themeName.trim() || "Untitled crossword",
          author: metadata.author,
          profile: layoutProfile,
          seed: searchSeed,
          searchAttempts: 150,
          answers: themeDrafts.map(({ answer }) => normalizeThemeAnswer(answer)),
        }),
      });
      const data = (await response.json()) as ThemeLayoutsResponse;
      if (!response.ok) throw new Error(data.error || "Theme layout search failed");
      setThemeLayouts(data.candidates);
      const firstViable = data.candidates.find((candidate) => candidate.analysis.viable);
      setSelectedThemeLayoutId(firstViable?.id ?? "");
      if (!firstViable) setThemeError(data.message);
    } catch (error) {
      setThemeError((error as Error).message);
    } finally {
      setThemeSearching(false);
    }
  };

  const reviewThemeLayout = () => {
    if (!selectedThemeLayout?.analysis.viable) {
      setThemeError("Choose a viable layout before continuing.");
      return;
    }
    setThemeError("");
    setThemeStep(3);
  };

  const placeThemesAndFill = () => {
    if (!selectedThemeLayout?.analysis.viable) {
      setThemeError("Choose a viable layout before constructing.");
      setThemeStep(2);
      return;
    }
    const hasLetters = grid.some((row) => row.some((cell) => Boolean(cell.letter)));
    if (
      hasLetters &&
      !window.confirm(
        "Use this theme layout? Existing blocks, letters, and clues will be replaced.",
      )
    ) {
      return;
    }

    const next = cloneGrid(selectedThemeLayout.cells);

    commitGrid(next);
    setClues({});
    setEntryScores({});
    setMetadata((current) => ({
      ...current,
      title: themeName.trim() || "Untitled crossword",
    }));
    const firstPlacement = selectedThemeLayout.placements[0];
    setSelected(
      firstPlacement ? [firstPlacement.row, firstPlacement.col] : [0, 0],
    );
    setDirection("A");
    setThemeWizardOpen(false);
    void fillGrid(next);
  };

  const generateBlockLayout = async () => {
    if (engine !== "ready" || busy || layoutBusy) return;
    const hasContent = grid.some((row) =>
      row.some((cell) => cell.black || Boolean(cell.letter)),
    );
    if (
      hasContent &&
      !window.confirm(
        `Generate a new ${layoutProfile} layout? This replaces all blocks and letters in the current grid.`,
      )
    ) {
      return;
    }

    setLayoutBusy(true);
    const layoutSeed = layoutSeedRef.current || Date.now();
    try {
      const response = await fetch(`${API_BASE}/layout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rows: grid.length,
          cols: grid[0].length,
          profile: layoutProfile,
          seed: layoutSeed,
          ...metadata,
        }),
      });
      const data = (await response.json()) as PuzzlePayload & { error?: string };
      if (!response.ok) throw new Error(data.error || "Layout generation failed");
      commitGrid(data.cells);
      setClues({});
      setEntryScores({});
      const firstWhite = data.cells
        .flatMap((row, rowIndex) =>
          row.map((cell, colIndex) => ({ cell, rowIndex, colIndex })),
        )
        .find(({ cell }) => !cell.black);
      if (firstWhite) setSelected([firstWhite.rowIndex, firstWhite.colIndex]);
      setDirection("A");
      layoutSeedRef.current = layoutSeed + 1;
    } catch (error) {
      window.alert((error as Error).message);
    } finally {
      setLayoutBusy(false);
    }
  };

  const resetToBlank = () => {
    if (!window.confirm("Start a blank 15×15 grid? Your current grid will be replaced.")) return;
    setGrid(blankGrid());
    setMetadata({ title: "Untitled crossword", author: "", copyright: "", note: "" });
    setClues({});
    setEntryScores({});
    setPast([]);
    setFuture([]);
    setSelected([0, 0]);
  };

  const exportAscii = () => {
    const lines = [
      String(grid.length),
      String(grid[0].length),
      metadata.title,
      metadata.author,
      metadata.copyright,
      metadata.note,
      ...grid.map((row) =>
        row.map((cell) => (cell.black ? "*" : cell.letter || "-")).join(""),
      ),
      ...entries.map(
        (entry) =>
          `${entry.id}: ${clues[entry.id] || ""} (${entry.pattern.replaceAll(".", "-")})`,
      ),
    ];
    downloadBlob(new Blob([lines.join("\n")], { type: "text/plain" }), "xwgen-puzzle.out");
  };

  const exportPuz = async () => {
    if (engine !== "ready") return;
    try {
      const response = await fetch(`${API_BASE}/export/puz`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      if (!response.ok) throw new Error("Could not export the .puz file.");
      downloadBlob(await response.blob(), "xwgen-puzzle.puz");
    } catch (error) {
      window.alert((error as Error).message);
    }
  };

  const importAscii = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const parsed = parseAscii(await file.text());
      loadPuzzle(parsed);
      setClues(parsed.clues);
    } catch (error) {
      window.alert((error as Error).message);
    } finally {
      event.target.value = "";
    }
  };

  const selectEntry = (entry: Entry) => {
    setSelected(entry.cells[0]);
    setDirection(entry.direction);
  };

  const selectedWordScore = (() => {
    if (!activeEntry || activeEntry.pattern.includes(".")) {
      return { value: "—", note: "Complete the entry to score it", state: "incomplete" };
    }
    if (candidateLoading) {
      return { value: "…", note: "Checking the word list", state: "loading" };
    }
    const selectedWord = activeCandidateData?.selectedWord;
    if (engine !== "ready") {
      return { value: "Unavailable", note: "Fill engine is offline", state: "unscored" };
    }
    if (!activeCandidateData || selectedWord?.word !== activeEntry.pattern) {
      return { value: "…", note: "Checking the word list", state: "loading" };
    }
    if (!selectedWord?.inLexicon) {
      return {
        value: "Not listed",
        note: lexicon?.source ?? "Active word list",
        state: "missing",
      };
    }
    if (!activeCandidateData?.lexicon.scored) {
      return {
        value: "Unscored",
        note: activeCandidateData?.lexicon.source ?? "Active word list",
        state: "unscored",
      };
    }
    return {
      value: String(selectedWord.score),
      note: activeCandidateData.lexicon.source,
      state: "scored",
    };
  })();

  const activeEntryHasLetters = Boolean(
    activeEntry?.cells.some(([row, col]) => grid[row][col].letter),
  );
  const activeEntryIsLocked = Boolean(
    activeEntryHasLetters &&
      activeEntry?.cells.every(
        ([row, col]) => !grid[row][col].letter || grid[row][col].locked,
      ),
  );

  const activeCellSet = new Set(activeEntry?.cells.map(([r, c]) => `${r}:${c}`) ?? []);
  const selectedCell = `${selected[0]}:${selected[1]}`;
  return (
    <main className="app-shell">
      <header className="masthead">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true"><span>X</span><span>W</span></div>
          <div>
            <p className="eyebrow">Crossword constructor</p>
            <h1>XWGen Studio</h1>
          </div>
        </div>
        <div className="document-actions">
          <button
            className={`fill-button header-fill-button ${busy ? "is-stopping" : ""}`}
            type="button"
            onClick={busy ? stopFill : () => void fillGrid()}
            disabled={engine !== "ready" || (!busy && layoutBusy)}
            aria-busy={busy}
          >
            <span aria-hidden="true">{busy ? "■" : "✦"}</span>
            {busy ? "Stop fill" : "Fill grid"}
          </button>
          <button
            className="quiet-button theme-wizard-button"
            type="button"
            onClick={openThemeWizard}
            disabled={busy || layoutBusy}
            aria-haspopup="dialog"
          >
            Theme wizard
          </button>
          <button className="quiet-button" type="button" onClick={resetToBlank}>New grid</button>
          <button className="quiet-button" type="button" onClick={() => fileInputRef.current?.click()}>Import</button>
          <div className="export-group">
            <button className="quiet-button" type="button" onClick={exportAscii}>Export ASCII</button>
            <button className="quiet-button" type="button" onClick={exportPuz} disabled={engine !== "ready"}>Export .puz</button>
          </div>
          <input ref={fileInputRef} className="visually-hidden" type="file" accept=".out,.txt" onChange={importAscii} />
        </div>
      </header>

      <div className="workspace">
        <aside className="left-rail" aria-label="Puzzle setup">
          <section className="left-panel-section puzzle-fields">
            <div className="left-section-header"><p className="eyebrow">Puzzle details</p></div>
            <div className="left-section-body">
              <label>
                <span>Title</span>
                <input
                  value={metadata.title}
                  onChange={(event) => setMetadata((current) => ({ ...current, title: event.target.value }))}
                  aria-label="Puzzle title"
                />
              </label>
              <label>
                <span>Constructor</span>
                <input
                  value={metadata.author}
                  placeholder="Your name"
                  onChange={(event) => setMetadata((current) => ({ ...current, author: event.target.value }))}
                  aria-label="Puzzle constructor"
                />
              </label>
            </div>
          </section>

          <section className="left-panel-section edit-controls">
            <div className="left-section-header">
              <p className="eyebrow">Grid tools</p>
              <div className="history-actions">
                <button type="button" onClick={undo} disabled={!past.length} aria-label="Undo" title="Undo">↶</button>
                <button type="button" onClick={redo} disabled={!future.length} aria-label="Redo" title="Redo">↷</button>
              </div>
            </div>
            <div className="left-section-body">
              <p className="control-note">Enter letters or draw black squares.</p>
              <div className="segmented-control" aria-label="Grid editing tool">
                <button className={tool === "type" ? "active" : ""} type="button" onClick={() => setTool("type")}>Type</button>
                <button className={tool === "block" ? "active" : ""} type="button" onClick={() => setTool("block")}>Blocks</button>
              </div>
              <label className="switch-label">
                <input type="checkbox" checked={symmetry} onChange={(event) => setSymmetry(event.target.checked)} />
                <span className="switch" aria-hidden="true" />
                180° rotational symmetry
              </label>
            </div>
          </section>

          <section className="left-panel-section block-layout-controls">
            <div className="left-section-header"><p className="eyebrow">Automatic layout</p></div>
            <div className="left-section-body">
              <p className="control-note">Build a connected, symmetric grid with 3+ letter entries.</p>
              <label className="select-control">
                <span>Block density</span>
                <select
                  value={layoutProfile}
                  onChange={(event) => setLayoutProfile(event.target.value as LayoutProfile)}
                  disabled={layoutBusy || busy}
                >
                  <option value="airy">Airy · ~12%</option>
                  <option value="classic">Classic · ~15%</option>
                  <option value="dense">Dense · ~17%</option>
                </select>
              </label>
              <button
                className="generate-layout-button"
                type="button"
                onClick={generateBlockLayout}
                disabled={engine !== "ready" || layoutBusy || busy}
              >
                {layoutBusy ? "Generating…" : "Generate new layout"}
              </button>
            </div>
          </section>

          <section className="left-panel-section fill-controls">
            <div className="left-section-header"><p className="eyebrow">Fill quality</p></div>
            <div className="left-section-body">
              <label className="select-control">
                <span>Dictionary policy</span>
                <select
                  value={qualityMode}
                  onChange={(event) => setQualityMode(event.target.value as QualityMode)}
                  disabled={busy}
                >
                  <option value="balanced">50+ then relax</option>
                  <option value="strict">Strict 50+</option>
                  <option value="open">All words</option>
                </select>
              </label>
              <p className="control-note quality-note">
                {qualityMode === "balanced"
                  ? "Start at 50+, then widen only when the grid needs it."
                  : qualityMode === "strict"
                    ? "Use only replaceable entries scored 50 or higher."
                    : "Allow the full word list immediately."}
              </p>
              <div className="cell-state-key" aria-label="Cell and letter color key">
                <span><i className="provisional" aria-hidden="true" />In progress</span>
                <span><i className="locked" aria-hidden="true" />Locked</span>
                <span><b className="score-swatch" aria-hidden="true">Ab</b>Low score</span>
              </div>
            </div>
          </section>

          <div className={`engine-state ${engine}`}>
            <span className="state-dot" aria-hidden="true" />
            {engine === "ready"
              ? lexicon?.scored
                ? "Scored lexicon ready"
                : "Unscored fallback"
              : engine === "checking"
                ? "Connecting…"
                : "Editor only"}
          </div>
        </aside>

        <section className="grid-workbench" aria-label="Crossword grid editor">

          <div
            className={`crossword-grid ${tool === "block" ? "block-mode" : ""}`}
            style={{ "--grid-cols": grid[0]?.length ?? 15 } as React.CSSProperties}
            aria-label={`${grid.length} by ${grid[0]?.length ?? 0} crossword grid`}
          >
            {numberedGrid.flatMap((row, rowIndex) =>
              row.map((cell, colIndex) => {
                const key = `${rowIndex}:${colIndex}`;
                const isSelected = key === selectedCell;
                const isActive = activeCellSet.has(key);
                const quality = cellQuality.get(key);
                const qualityDescription = quality
                  ? `, lowest crossing word score ${quality.score} from ${quality.entries.join(" and ")}`
                  : "";
                return (
                  <button
                    key={key}
                    type="button"
                    className={`grid-cell ${cell.black ? "black" : ""} ${cell.letter && !cell.locked ? "provisional" : ""} ${isActive ? "in-entry" : ""} ${isSelected ? "selected" : ""} ${cell.locked ? "locked" : ""} ${colIndex === row.length - 1 ? "last-column" : ""} ${rowIndex === numberedGrid.length - 1 ? "last-row" : ""}`}
                    onClick={() => selectCell(rowIndex, colIndex)}
                    onKeyDown={handleCellKeyDown}
                    aria-label={cell.black ? `Block at row ${rowIndex + 1}, column ${colIndex + 1}` : `Row ${rowIndex + 1}, column ${colIndex + 1}${cell.letter ? `, ${cell.letter}` : ""}${qualityDescription}`}
                    title={quality ? `Lowest crossing word score: ${quality.score} (${quality.entries.join(", ")})` : undefined}
                    tabIndex={isSelected ? 0 : -1}
                  >
                    {!cell.black && cell.number ? <span className="cell-number">{cell.number}</span> : null}
                    {!cell.black ? (
                      <span
                        className={`cell-letter ${quality ? "quality-scored" : ""}`}
                        style={quality ? { color: qualityLetterColor(quality.score) } : undefined}
                      >
                        {cell.letter}
                      </span>
                    ) : null}
                  </button>
                );
              }),
            )}
          </div>

        </section>

        <aside className="right-rail" aria-label="Entry editor and puzzle clues">
          {activeEntry ? (
            <section className="compact-entry-editor" aria-label={`Selected entry ${activeEntry.id}`}>
              <div className="entry-strip">
                <strong
                  className="entry-id"
                  title={`${activeEntry.number} ${activeEntry.direction === "A" ? "Across" : "Down"}`}
                >
                  {activeEntry.id}
                </strong>
                <span className="compact-pattern" aria-label={`Pattern ${activeEntry.pattern}`}>
                  {activeEntry.pattern.replaceAll(".", "·")}
                </span>
                <span
                  className={`compact-score ${selectedWordScore.state}`}
                  title={`Wordlist score: ${selectedWordScore.value}. ${selectedWordScore.note}`}
                  aria-label={`Wordlist score ${selectedWordScore.value}`}
                >
                  <small>Score</small>
                  <b>{selectedWordScore.value}</b>
                </span>
                <button
                  className={`entry-lock-icon ${activeEntryIsLocked ? "locked" : "unlocked"}`}
                  type="button"
                  onClick={toggleActiveLock}
                  disabled={!activeEntryHasLetters}
                  aria-pressed={activeEntryIsLocked}
                  aria-label={activeEntryIsLocked ? "Unlock filled letters in this entry" : "Lock filled letters in this entry"}
                  title={activeEntryIsLocked ? "Unlock filled letters" : "Lock filled letters"}
                >
                  <span aria-hidden="true" />
                </button>
              </div>

              <label className="compact-clue-field">
                <span className="visually-hidden">Clue for {activeEntry.id}</span>
                <input
                  value={clues[activeEntry.id] ?? ""}
                  placeholder={`Clue for ${activeEntry.id}…`}
                  onChange={(event) => setClues((current) => ({ ...current, [activeEntry.id]: event.target.value }))}
                />
              </label>

              <details className="candidate-drawer">
                <summary>
                  <span>Candidate fill</span>
                  <strong>
                    {candidateLoading
                      ? "Checking…"
                      : activeCandidateData
                        ? activeCandidateData.total.toLocaleString()
                        : "Unavailable"}
                  </strong>
                  <small>{activeCandidateData?.lexicon.source ?? lexicon?.source ?? "Dictionary"}</small>
                </summary>
                <div className="candidate-list" aria-live="polite">
                  {activeCandidateData?.candidates.map((candidate, index) => (
                    <button
                      type="button"
                      key={candidate.word}
                      onClick={() => applyCandidate(candidate.word)}
                    >
                      <span>{candidate.word}</span>
                      <span className="candidate-meta">
                        <small>{String(index + 1).padStart(2, "0")}</small>
                        {activeCandidateData.lexicon.scored ? (
                          <b title="Word quality score">{candidate.score}</b>
                        ) : null}
                      </span>
                    </button>
                  ))}
                  {!candidateLoading && activeCandidateData?.candidates.length === 0 ? (
                    <p className="empty-state">No words match the locked letters in this entry.</p>
                  ) : null}
                  {engine === "offline" ? (
                    <p className="empty-state">Start the local fill engine to inspect candidates.</p>
                  ) : null}
                </div>
                {activeCandidateData?.lexicon.source === "Spread the Word(list)" ? (
                  <p className="lexicon-credit">
                    Word quality by{" "}
                    <a href="https://www.spreadthewordlist.com/" target="_blank" rel="noreferrer">
                      Spread the Word(list)
                    </a>{" "}
                    · CC BY-NC-SA 4.0
                  </p>
                ) : null}
              </details>
            </section>
          ) : (
            <p className="empty-state">Select a white square to inspect its entry.</p>
          )}

          <section className="clue-panel" aria-labelledby="puzzle-clues-heading">
            <div className="clue-sheet-heading">
              <h2 id="puzzle-clues-heading">Puzzle clues</h2>
              <span className={missingClueCount ? "clue-progress incomplete" : "clue-progress complete"}>
                {missingClueCount ? `${missingClueCount} missing` : "Complete"}
              </span>
            </div>
            <div className="clue-columns">
              {([
                ["Across", acrossEntries],
                ["Down", downEntries],
              ] as const).map(([heading, clueEntries]) => (
                <section
                  className="clue-column"
                  key={heading}
                  aria-labelledby={`${heading.toLowerCase()}-clues-heading`}
                >
                  <h3 id={`${heading.toLowerCase()}-clues-heading`}>{heading}</h3>
                  <ol>
                    {clueEntries.map((entry) => {
                      const clue = clues[entry.id]?.trim();
                      const isActive = entry.id === activeEntry?.id;
                      return (
                        <li key={entry.id}>
                          <button
                            type="button"
                            className={`${isActive ? "active" : ""} ${clue ? "" : "missing"}`}
                            onClick={() => selectEntry(entry)}
                            aria-label={`${entry.number} ${heading}: ${clue || "clue needed"}`}
                          >
                            <strong>{entry.number}</strong>
                            <span>{clue || "Clue needed"}</span>
                            {!clue ? <small>Missing</small> : null}
                          </button>
                        </li>
                      );
                    })}
                  </ol>
                </section>
              ))}
            </div>
          </section>
        </aside>
      </div>

      {themeWizardOpen ? (
        <div
          className="theme-wizard-backdrop"
          onMouseDown={(event) => {
            if (event.currentTarget === event.target && !busy && !themeSearching) {
              setThemeWizardOpen(false);
            }
          }}
        >
          <section
            className="theme-wizard"
            role="dialog"
            aria-modal="true"
            aria-labelledby="theme-wizard-title"
          >
            <header className="theme-wizard-header">
              <div>
                <p className="eyebrow">Themed puzzle</p>
                <h2 id="theme-wizard-title">Build around your best answers</h2>
              </div>
              <button
                className="theme-close-button"
                type="button"
                onClick={() => setThemeWizardOpen(false)}
                aria-label="Close theme wizard"
                disabled={busy || themeSearching}
              >
                ×
              </button>
            </header>

            <ol className="theme-steps" aria-label="Theme wizard progress">
              {(["Themes", "Layouts", "Fill"] as const).map((label, index) => {
                const step = (index + 1) as 1 | 2 | 3;
                return (
                  <li
                    className={step === themeStep ? "active" : step < themeStep ? "complete" : ""}
                    key={label}
                    aria-current={step === themeStep ? "step" : undefined}
                  >
                    <span>{step}</span>{label}
                  </li>
                );
              })}
            </ol>

            <div className="theme-wizard-body">
              {themeStep === 1 ? (
                <div className="theme-step-content">
                  <div className="theme-step-heading">
                    <h3>Start with the theme answers</h3>
                    <p>
                      Enter the phrases you want to keep. We’ll search the current grid and new standard layouts for supportive crossings.
                    </p>
                  </div>
                  <label className="theme-name-field">
                    <span>
                      <strong>Theme / puzzle title</strong>
                      <small>This will become the puzzle title.</small>
                    </span>
                    <input
                      value={themeName}
                      placeholder="e.g. Under the Sea"
                      maxLength={255}
                      onChange={(event) => setThemeName(event.target.value)}
                    />
                  </label>
                  <div className="theme-count-options" aria-label="Number of theme answers">
                    {([4, 5, 6] as ThemeCount[]).map((count) => (
                      <button
                        className={themeCount === count ? "active" : ""}
                        type="button"
                        key={count}
                        onClick={() => changeThemeCount(count)}
                        aria-pressed={themeCount === count}
                      >
                        <strong>{count}</strong>
                        <span>answers</span>
                      </button>
                    ))}
                  </div>
                  <div className="theme-answer-list theme-answer-entry-list">
                    {themeDrafts.map(({ answer }, index) => {
                      const normalized = normalizeThemeAnswer(answer);
                      const complete = normalized.length >= 3;
                      return (
                        <label className={complete ? "complete" : ""} key={index}>
                          <span className="theme-answer-slot">
                            <strong>Theme {index + 1}</strong>
                            <small>3–{grid[0]?.length ?? 15} letters</small>
                          </span>
                          <input
                            value={normalized}
                            maxLength={grid[0]?.length ?? 15}
                            placeholder="Enter answer"
                            autoComplete="off"
                            spellCheck={false}
                            onChange={(event) => {
                              const nextAnswer = normalizeThemeAnswer(event.target.value);
                              setThemeDrafts((current) =>
                                current.map((draft, draftIndex) =>
                                  draftIndex === index
                                    ? { ...draft, answer: nextAnswer }
                                    : draft,
                                ),
                              );
                              setThemeLayouts([]);
                              setSelectedThemeLayoutId("");
                              setThemeError("");
                            }}
                            aria-label={`Theme answer ${index + 1}`}
                          />
                          <span className="theme-answer-count">
                            {normalized.length || "—"}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                  <p className="theme-entry-note">
                    Theme answers can be custom phrases or proper names; they do not need to appear in the fill dictionary.
                  </p>
                </div>
              ) : null}

              {themeStep === 2 ? (
                <div className="theme-step-content">
                  <div className="theme-step-heading theme-layout-heading">
                    <div>
                      <h3>Choose a fillable layout</h3>
                      <p>Each option has already passed dictionary propagation; verified choices also completed a short test fill.</p>
                    </div>
                    {!themeSearching && themeLayouts.length ? (
                      <button className="quiet-button" type="button" onClick={() => void findThemeLayouts()}>
                        Try other layouts
                      </button>
                    ) : null}
                  </div>
                  <div className="theme-name-banner">
                    <span>Theme</span>
                    <strong>{themeName.trim() || "Untitled theme"}</strong>
                  </div>
                  <div className="theme-answer-summary">
                    {themeDrafts.map(({ answer }, index) => (
                      <span key={index}><b>{normalizeThemeAnswer(answer)}</b>{normalizeThemeAnswer(answer).length}</span>
                    ))}
                  </div>

                  {themeSearching ? (
                    <div className="theme-searching" aria-live="polite">
                      <span className="theme-search-spinner" aria-hidden="true" />
                      <div>
                        <h3>Building around your themes…</h3>
                        <p>Trying placements, standard block patterns, arc consistency, and short test fills.</p>
                      </div>
                    </div>
                  ) : null}

                  {!themeSearching && themeLayouts.length ? (
                    <div className="theme-layout-options" role="radiogroup" aria-label="Theme layout choices">
                      {themeLayouts.map((candidate, index) => {
                        const selectedLayout = candidate.id === selectedThemeLayoutId;
                        const blocked = !candidate.analysis.viable;
                        return (
                          <button
                            className={`theme-layout-card ${selectedLayout ? "selected" : ""} ${blocked ? "blocked" : ""}`}
                            type="button"
                            role="radio"
                            aria-checked={selectedLayout}
                            key={candidate.id}
                            onClick={() => {
                              setSelectedThemeLayoutId(candidate.id);
                              setThemeError("");
                            }}
                            disabled={blocked}
                          >
                            <div
                              className="theme-mini-grid"
                              style={{ "--preview-cols": candidate.cols } as React.CSSProperties}
                              aria-hidden="true"
                            >
                              {candidate.cells.flatMap((row, rowIndex) =>
                                row.map((cell, colIndex) => (
                                  <span
                                    className={`${cell.black ? "black" : ""} ${cell.locked ? "theme" : ""}`}
                                    key={`${rowIndex}:${colIndex}`}
                                  />
                                )),
                              )}
                            </div>
                            <span className="theme-layout-card-copy">
                              <span className="theme-layout-card-title">
                                <strong>{candidate.layout.currentLayout ? "Current grid" : `Option ${index + 1}`}</strong>
                                <b className={candidate.analysis.verification}>{candidate.analysis.rating}</b>
                              </span>
                              <span className="theme-layout-metrics">
                                <small>{candidate.layout.blockCount} blocks</small>
                                <small>Fit score {Math.round(candidate.analysis.score)}</small>
                                <small>Min support {candidate.analysis.minimumDomain}</small>
                              </span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  ) : null}

                  {!themeSearching && selectedThemeLayout ? (
                    <div className="theme-placement-preview">
                      {selectedThemeLayout.placements.map((placement) => (
                        <span key={placement.answerIndex}>
                          <b>{placement.answer}</b>
                          <small>{placement.entryId} · {placement.length} letters</small>
                          <em className={placement.label.toLowerCase()}>{placement.label}</em>
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}

              {themeStep === 3 && selectedThemeLayout ? (
                <div className="theme-step-content">
                  <div className="theme-step-heading">
                    <h3>Ready to construct</h3>
                    <p>
                      The selected pattern supports every theme crossing. Theme answers will stay locked while the quality-aware CSP filler completes the grid.
                    </p>
                  </div>
                  <div className="theme-final-layout-summary">
                    <div
                      className="theme-mini-grid large"
                      style={{ "--preview-cols": selectedThemeLayout.cols } as React.CSSProperties}
                      aria-label="Selected theme layout preview"
                    >
                      {selectedThemeLayout.cells.flatMap((row, rowIndex) =>
                        row.map((cell, colIndex) => (
                          <span
                            className={`${cell.black ? "black" : ""} ${cell.locked ? "theme" : ""}`}
                            key={`${rowIndex}:${colIndex}`}
                          />
                        )),
                      )}
                    </div>
                    <div>
                      <p className="eyebrow">Preflight result</p>
                      <h3>{selectedThemeLayout.analysis.rating}</h3>
                      <p>{selectedThemeLayout.analysis.message}</p>
                    </div>
                  </div>
                  <div className="theme-review-list">
                    {selectedThemeLayout.placements.map((placement) => (
                      <div key={placement.answerIndex}>
                        <span><b>{placement.entryId}</b>{placement.length}</span>
                        <strong>{placement.answer}</strong>
                        <em className={placement.label.toLowerCase()}>{placement.label}</em>
                      </div>
                    ))}
                  </div>
                  <div className="theme-fill-note">
                    <span aria-hidden="true">✓</span>
                    If the quality-first search still times out, the theme grid remains in the editor so you can retry with a wider dictionary or another layout.
                  </div>
                </div>
              ) : null}

              {themeError ? <p className="theme-error" role="alert">{themeError}</p> : null}
              {themeStep === 3 && engine !== "ready" ? (
                <p className="theme-error" role="alert">Start the local fill engine before constructing.</p>
              ) : null}
            </div>

            <footer className="theme-wizard-footer">
              <button
                className="quiet-button"
                type="button"
                disabled={themeSearching}
                onClick={() => {
                  if (themeStep === 1) setThemeWizardOpen(false);
                  else {
                    setThemeStep((themeStep - 1) as 1 | 2);
                    setThemeError("");
                  }
                }}
              >
                {themeStep === 1 ? "Cancel" : "Back"}
              </button>
              {themeStep === 1 ? (
                <button
                  className="theme-primary-button"
                  type="button"
                  onClick={() => void findThemeLayouts()}
                  disabled={engine !== "ready" || themeSearching}
                >
                  Find layouts
                </button>
              ) : null}
              {themeStep === 2 ? (
                <button
                  className="theme-primary-button"
                  type="button"
                  onClick={reviewThemeLayout}
                  disabled={themeSearching || !selectedThemeLayout?.analysis.viable}
                >
                  Review layout
                </button>
              ) : null}
              {themeStep === 3 ? (
                <button
                  className="theme-primary-button"
                  type="button"
                  onClick={placeThemesAndFill}
                  disabled={engine !== "ready" || busy || !selectedThemeLayout?.analysis.viable}
                >
                  Use layout &amp; fill
                </button>
              ) : null}
            </footer>
          </section>
        </div>
      ) : null}

    </main>
  );
}
