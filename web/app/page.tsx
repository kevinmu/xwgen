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

type PuzzlePayload = {
  rows: number;
  cols: number;
  title: string;
  author: string;
  copyright: string;
  note: string;
  cells: Cell[][];
  entries?: Array<{ id: string; clue: string }>;
  warnings?: string[];
  result?: FillStats;
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
};

type CandidateResponse = {
  entryId: string;
  pattern: string;
  total: number;
  candidates: string[];
};

const API_BASE =
  process.env.NEXT_PUBLIC_XWGEN_API ?? "http://127.0.0.1:8765/api";

const cloneGrid = (cells: Cell[][]): Cell[][] =>
  cells.map((row) => row.map((cell) => ({ ...cell })));

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
  const [selected, setSelected] = useState<[number, number]>([0, 0]);
  const [direction, setDirection] = useState<Direction>("A");
  const [tool, setTool] = useState<"type" | "block">("type");
  const [symmetry, setSymmetry] = useState(true);
  const [engine, setEngine] = useState<"checking" | "ready" | "offline">("checking");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Loading the sample puzzle…");
  const [warnings, setWarnings] = useState<string[]>([]);
  const [stats, setStats] = useState<FillStats | null>(null);
  const [candidateData, setCandidateData] = useState<CandidateResponse | null>(null);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [past, setPast] = useState<Cell[][][]>([]);
  const [future, setFuture] = useState<Cell[][][]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const derived = useMemo(() => deriveEntries(grid), [grid]);
  const numberedGrid = derived.cells;
  const entries = derived.entries;

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
    setWarnings(puzzle.warnings ?? []);
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
        const response = await fetch(`${API_BASE}/sample`);
        if (!response.ok) throw new Error("sample unavailable");
        const sample = (await response.json()) as PuzzlePayload;
        if (cancelled) return;
        setEngine("ready");
        loadPuzzle(sample);
        setStatus("Sample loaded. Select an entry or press Fill grid.");
      } catch {
        if (cancelled) return;
        setEngine("offline");
        setStatus("The editor is ready, but the fill engine is not connected.");
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
        if (!cancelled) setCandidateData(data);
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
      setStats(null);
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
    setStatus(newValue ? "Block added." : "Block removed.");
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
    commitGrid(next);
    setStatus(`${word} set as ${activeEntry.id} and locked.`);
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
    setStatus(`${activeEntry.id} ${shouldLock ? "locked" : "unlocked"}.`);
  };

  const fillGrid = async () => {
    if (engine !== "ready" || busy) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setStats(null);
    setStatus("Searching for a consistent fill…");
    try {
      const response = await fetch(`${API_BASE}/fill`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          ...buildPayload(),
          options: { timeout: 30, nodesPerRestart: 50000, restarts: 4, seed: 0 },
        }),
      });
      const data = (await response.json()) as PuzzlePayload & { error?: string };
      if (!response.ok) throw new Error(data.error || "Fill request failed");
      if (data.result?.status === "solved") {
        commitGrid(data.cells);
        setClues((current) => {
          const next = { ...current };
          data.entries?.forEach((entry) => {
            next[entry.id] = entry.clue;
          });
          return next;
        });
        setStatus(`Fill complete in ${data.result.elapsedSeconds.toFixed(2)} seconds.`);
      } else {
        setStatus(data.result?.message || "No valid fill was found.");
      }
      setStats(data.result ?? null);
      setWarnings(data.warnings ?? []);
    } catch (error) {
      if ((error as Error).name === "AbortError") setStatus("Fill stopped.");
      else setStatus((error as Error).message);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  };

  const stopFill = () => abortRef.current?.abort();

  const resetToBlank = () => {
    if (!window.confirm("Start a blank 15×15 grid? Your current grid will be replaced.")) return;
    setGrid(blankGrid());
    setMetadata({ title: "Untitled crossword", author: "", copyright: "", note: "" });
    setClues({});
    setWarnings([]);
    setStats(null);
    setPast([]);
    setFuture([]);
    setSelected([0, 0]);
    setStatus("Blank 15×15 grid ready.");
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
    setStatus("ASCII puzzle exported.");
  };

  const exportPuz = async () => {
    if (engine !== "ready") return;
    setStatus("Preparing .puz file…");
    try {
      const response = await fetch(`${API_BASE}/export/puz`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload()),
      });
      if (!response.ok) throw new Error("Could not export the .puz file.");
      downloadBlob(await response.blob(), "xwgen-puzzle.puz");
      setStatus(".puz file exported.");
    } catch (error) {
      setStatus((error as Error).message);
    }
  };

  const importAscii = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const parsed = parseAscii(await file.text());
      loadPuzzle(parsed);
      setClues(parsed.clues);
      setStatus(`${file.name} imported.`);
    } catch (error) {
      setStatus((error as Error).message);
    } finally {
      event.target.value = "";
    }
  };

  const activeCellSet = new Set(activeEntry?.cells.map(([r, c]) => `${r}:${c}`) ?? []);
  const selectedCell = `${selected[0]}:${selected[1]}`;
  const lockedCount = grid.flat().filter((cell) => cell.locked).length;
  const filledCount = grid.flat().filter((cell) => !cell.black && cell.letter).length;
  const openCount = grid.flat().filter((cell) => !cell.black).length;

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
          <button className="quiet-button" type="button" onClick={resetToBlank}>New grid</button>
          <button className="quiet-button" type="button" onClick={() => fileInputRef.current?.click()}>Import</button>
          <div className="export-group">
            <button className="quiet-button" type="button" onClick={exportAscii}>Export ASCII</button>
            <button className="quiet-button" type="button" onClick={exportPuz} disabled={engine !== "ready"}>Export .puz</button>
          </div>
          <input ref={fileInputRef} className="visually-hidden" type="file" accept=".out,.txt" onChange={importAscii} />
        </div>
      </header>

      <section className="title-strip" aria-label="Puzzle details">
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
        <div className={`engine-state ${engine}`}>
          <span className="state-dot" aria-hidden="true" />
          {engine === "ready" ? "Fill engine ready" : engine === "checking" ? "Connecting…" : "Editor only"}
        </div>
      </section>

      <div className="workspace">
        <section className="grid-workbench" aria-label="Crossword grid editor">
          <div className="tool-rail">
            <div className="segmented-control" aria-label="Grid editing tool">
              <button className={tool === "type" ? "active" : ""} type="button" onClick={() => setTool("type")}>Type</button>
              <button className={tool === "block" ? "active" : ""} type="button" onClick={() => setTool("block")}>Blocks</button>
            </div>
            <label className="switch-label">
              <input type="checkbox" checked={symmetry} onChange={(event) => setSymmetry(event.target.checked)} />
              <span className="switch" aria-hidden="true" />
              180° symmetry
            </label>
            <div className="history-actions">
              <button type="button" onClick={undo} disabled={!past.length} aria-label="Undo" title="Undo">↶</button>
              <button type="button" onClick={redo} disabled={!future.length} aria-label="Redo" title="Redo">↷</button>
            </div>
          </div>

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
                return (
                  <button
                    key={key}
                    type="button"
                    className={`grid-cell ${cell.black ? "black" : ""} ${isActive ? "in-entry" : ""} ${isSelected ? "selected" : ""} ${cell.locked ? "locked" : ""}`}
                    onClick={() => selectCell(rowIndex, colIndex)}
                    onKeyDown={handleCellKeyDown}
                    aria-label={cell.black ? `Block at row ${rowIndex + 1}, column ${colIndex + 1}` : `Row ${rowIndex + 1}, column ${colIndex + 1}${cell.letter ? `, ${cell.letter}` : ""}`}
                    tabIndex={isSelected ? 0 : -1}
                  >
                    {!cell.black && cell.number ? <span className="cell-number">{cell.number}</span> : null}
                    {!cell.black ? <span className="cell-letter">{cell.letter}</span> : null}
                    {!cell.black && cell.locked ? <span className="lock-mark" aria-hidden="true" /> : null}
                  </button>
                );
              }),
            )}
          </div>

          <div className="grid-caption">
            <span>{filledCount}/{openCount} letters</span>
            <span>{lockedCount} locked</span>
            <span>{entries.length} entries</span>
          </div>
        </section>

        <aside className="inspector" aria-label="Entry inspector">
          <div className="entry-heading">
            <div>
              <p className="eyebrow">Selected entry</p>
              <h2>{activeEntry ? `${activeEntry.number} ${activeEntry.direction === "A" ? "Across" : "Down"}` : "No entry"}</h2>
            </div>
            {activeEntry ? <span className="length-badge">{activeEntry.length} letters</span> : null}
          </div>

          {activeEntry ? (
            <>
              <div className="pattern" aria-label={`Pattern ${activeEntry.pattern}`}>
                {[...activeEntry.pattern].map((letter, index) => (
                  <span key={`${activeEntry.id}-${index}`} className={letter === "." ? "empty" : ""}>{letter === "." ? "" : letter}</span>
                ))}
              </div>
              <label className="clue-field">
                <span>Clue</span>
                <textarea
                  rows={2}
                  value={clues[activeEntry.id] ?? ""}
                  placeholder="Write a clue…"
                  onChange={(event) => setClues((current) => ({ ...current, [activeEntry.id]: event.target.value }))}
                />
              </label>
              <button className="entry-lock-button" type="button" onClick={toggleActiveLock}>
                {activeEntry.cells.some(([r, c]) => grid[r][c].letter && !grid[r][c].locked) ? "Lock this entry" : "Unlock this entry"}
              </button>

              <div className="candidate-header">
                <div>
                  <p className="eyebrow">Dictionary matches</p>
                  <strong>{candidateLoading ? "Checking…" : candidateData ? `${candidateData.total.toLocaleString()} candidates` : "Unavailable"}</strong>
                </div>
                <span>locked letters only</span>
              </div>
              <div className="candidate-list" aria-live="polite">
                {candidateData?.candidates.map((word, index) => (
                  <button type="button" key={word} onClick={() => applyCandidate(word)}>
                    <span>{word}</span><small>{String(index + 1).padStart(2, "0")}</small>
                  </button>
                ))}
                {!candidateLoading && candidateData?.candidates.length === 0 ? (
                  <p className="empty-state">No words match the locked letters in this entry.</p>
                ) : null}
                {engine === "offline" ? (
                  <p className="empty-state">Start the local fill engine to inspect candidates.</p>
                ) : null}
              </div>
            </>
          ) : (
            <p className="empty-state">Select a white square to inspect its entry.</p>
          )}
        </aside>
      </div>

      <section className="run-bar" aria-live="polite">
        <div className="run-status">
          <span className={`run-indicator ${busy ? "searching" : stats?.status === "solved" ? "solved" : ""}`} aria-hidden="true" />
          <div><p>{status}</p>{stats ? <small>{stats.nodes.toLocaleString()} nodes · {stats.backjumps.toLocaleString()} backjumps · {stats.propagations.toLocaleString()} propagations</small> : <small>Unlocked letters are replaced on the next fill.</small>}</div>
        </div>
        {warnings.length ? <span className="warning-count" title={warnings.join("\n")}>{warnings.length} grid {warnings.length === 1 ? "warning" : "warnings"}</span> : null}
        <div className="run-actions">
          {busy ? <button className="stop-button" type="button" onClick={stopFill}>Stop</button> : null}
          <button className="fill-button" type="button" onClick={fillGrid} disabled={engine !== "ready" || busy}>
            <span aria-hidden="true">✦</span> Fill grid
          </button>
        </div>
      </section>
    </main>
  );
}
