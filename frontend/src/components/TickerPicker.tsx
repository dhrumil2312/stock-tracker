import { useEffect, useId, useRef, useState } from "react";
import type { TickerSummary } from "../types";

interface Props {
  tickers: TickerSummary[];
  query: string;
  onQueryChange: (query: string) => void;
  onPick: (ticker: string) => void;
  disabled?: boolean;
}

export default function TickerPicker({
  tickers,
  query,
  onQueryChange,
  onPick,
  disabled = false,
}: Props) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);

  const needle = query.trim().toUpperCase();
  const filtered = needle
    ? tickers.filter(
        (t) =>
          t.ticker.includes(needle) ||
          (t.name ?? "").toUpperCase().includes(needle) ||
          (t.sector ?? "").toUpperCase().includes(needle)
      )
    : tickers;
  const active = filtered[Math.min(highlight, Math.max(filtered.length - 1, 0))];

  useEffect(() => {
    function onPointerDown(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  function pick(ticker: string) {
    onQueryChange(ticker);
    setOpen(false);
    onPick(ticker);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setHighlight((i) => Math.min(i + 1, Math.max(filtered.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setHighlight((i) => Math.max(i - 1, 0));
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "Enter" && open && active) {
      event.preventDefault();
      pick(active.ticker);
    }
  }

  return (
    <div className="ticker-picker" ref={rootRef}>
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={open && active ? `${listId}-${active.ticker}` : undefined}
        autoComplete="off"
        spellCheck={false}
        value={query}
        disabled={disabled}
        placeholder="Search ticker"
        onChange={(e) => {
          onQueryChange(e.target.value.toUpperCase());
          setHighlight(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && !disabled && (
        <ul id={listId} role="listbox" className="ticker-menu">
          {filtered.length === 0 && <li className="ticker-empty">No matching seeded ticker</li>}
          {filtered.map((t) => (
            <li
              key={t.ticker}
              id={`${listId}-${t.ticker}`}
              role="option"
              aria-selected={active?.ticker === t.ticker}
              className={`ticker-option${active?.ticker === t.ticker ? " active" : ""}`}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setHighlight(filtered.indexOf(t))}
              onClick={() => pick(t.ticker)}
            >
              <span className="ticker-sym">{t.ticker}</span>
              <span className="ticker-name">{t.name ?? t.ticker}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
