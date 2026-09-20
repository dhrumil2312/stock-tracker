import { useEffect, useRef, useState } from "react";
import { fetchMoveNews, fetchTicker, fetchTickers } from "./api";
import BrandMark from "./components/BrandMark";
import ChatPanel from "./components/ChatPanel";
import MovementList from "./components/MovementList";
import PriceChart from "./components/PriceChart";
import TickerPicker from "./components/TickerPicker";
import type { TickerResponse, TickerSummary } from "./types";

const CHAT_MIN = 300;
const CHAT_MAX = 720;
const CHAT_DEFAULT = 400;
const CHAT_OPEN_KEY = "vt-chat-open";
const CHAT_WIDTH_KEY = "vt-chat-width";

export default function App() {
  const [tickers, setTickers] = useState<TickerSummary[]>([]);
  const [query, setQuery] = useState("");
  const [data, setData] = useState<TickerResponse | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [newsLoading, setNewsLoading] = useState(false);
  const [newsError, setNewsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(() => readStoredFlag(CHAT_OPEN_KEY, true));
  const [chatWidth, setChatWidth] = useState(() =>
    readStoredNumber(CHAT_WIDTH_KEY, CHAT_DEFAULT, CHAT_MIN, CHAT_MAX)
  );
  const newsReq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    fetchTickers()
      .then((rows) => {
        if (!cancelled) setTickers(rows);
      })
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    writeStored(CHAT_OPEN_KEY, chatOpen ? "1" : "0");
  }, [chatOpen]);

  useEffect(() => {
    writeStored(CHAT_WIDTH_KEY, String(chatWidth));
  }, [chatWidth]);

  async function load(symbol: string) {
    const ticker = symbol.trim().toUpperCase();
    const allowed = tickers.some((t) => t.ticker === ticker);
    if (!allowed) {
      setError("Pick a ticker from the seeded list.");
      return;
    }
    setLoading(true);
    setError(null);
    setSelected(null);
    setNewsError(null);
    setNewsLoading(false);
    newsReq.current += 1;
    try {
      const res = await fetchTicker(ticker);
      setData(res);
    } catch (err) {
      setError((err as Error).message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function loadNews(date: string) {
    if (!data) return;
    const reqId = ++newsReq.current;
    setSelected(date);
    setNewsError(null);
    setNewsLoading(true);
    try {
      const day = await fetchMoveNews(data.ticker, date);
      if (reqId !== newsReq.current) return;
      const articles = day.movements.find((m) => m.date === date)?.articles ?? [];
      setData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          movements: prev.movements.map((m) => (m.date === date ? { ...m, articles } : m)),
        };
      });
    } catch (err) {
      if (reqId !== newsReq.current) return;
      setNewsError((err as Error).message);
    } finally {
      if (reqId === newsReq.current) setNewsLoading(false);
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    void load(query);
  }

  const displayName =
    data?.company_name && data.company_name !== data.ticker ? data.company_name : data?.ticker;
  const metaBits = [data?.exchange, data?.sector, data?.industry].filter(Boolean);
  const lastBar = data?.prices.length ? data.prices[data.prices.length - 1] : undefined;
  const lastChange = lastBar?.pct_change ?? null;
  const selectedMove = data?.movements.find((m) => m.date === selected) ?? null;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <BrandMark />
          <h1>Volatility Tracker</h1>
        </div>
        <form className="topbar-search" onSubmit={onSubmit}>
          <label className="ticker-field">
            <span className="visually-hidden">Ticker</span>
            <TickerPicker
              tickers={tickers}
              query={query}
              onQueryChange={setQuery}
              onPick={(ticker) => void load(ticker)}
              disabled={listLoading}
            />
          </label>
        </form>
        <button
          type="button"
          className={`chat-toggle${chatOpen ? " is-open" : ""}`}
          aria-pressed={chatOpen}
          aria-controls="ticker-chat"
          title={chatOpen ? "Hide chat" : "Show chat"}
          onClick={() => setChatOpen((open) => !open)}
        >
          <ChatIcon />
          <span>{chatOpen ? "Hide chat" : "Chat"}</span>
        </button>
      </header>

      <div
        className={`workspace${chatOpen ? "" : " chat-closed"}`}
        style={{ "--chat-width": `${chatWidth}px` } as React.CSSProperties}
      >
        <main className="main">
          {error && <div className="error">{error}</div>}

          {!data && !loading && (
            <div className="empty-state">
              <h2>Track a ticker’s volatility</h2>
              <p>Search a seeded ticker, then ask in chat. Load news on a day if you want the headlines.</p>
            </div>
          )}

          {data && (
            <>
              <section className="quote">
                <div>
                  <h2 className="quote-name">
                    {displayName}
                    {displayName !== data.ticker && <span className="quote-symbol">{data.ticker}</span>}
                  </h2>
                  <div className="quote-meta">
                    {metaBits.length ? `${metaBits.join(" · ")} · ` : ""}
                    {data.movements.length} day{data.movements.length === 1 ? "" : "s"} ≥ {data.threshold}%
                    {loading ? " · Updating…" : ""}
                  </div>
                </div>
                {lastBar && (
                  <div className="quote-last">
                    <div className="quote-price">{formatPrice(lastBar.close)}</div>
                    {lastChange != null && (
                      <div className={`quote-change ${lastChange >= 0 ? "up" : "down"}`}>
                        {lastChange > 0 ? "+" : ""}
                        {lastChange.toFixed(2)}%
                      </div>
                    )}
                  </div>
                )}
              </section>

              <section className="panel">
                <PriceChart
                  prices={data.prices}
                  movements={data.movements}
                  selected={selected}
                  onSelectMovement={(date) => void loadNews(date)}
                />
              </section>

              <section>
                <div className="section-head">
                  <h2>Days that moved more than 2%</h2>
                  <span className="muted">{data.movements.length} in this window</span>
                </div>
                <MovementList
                  movements={data.movements}
                  selected={selected}
                  newsLoading={newsLoading}
                  newsError={newsError}
                  onLoadNews={(date) => void loadNews(date)}
                />
              </section>
            </>
          )}
        </main>

        <aside
          id="ticker-chat"
          className="chat-sidebar"
          aria-label="Ticker chat"
          hidden={!chatOpen}
        >
          <div
            className="chat-resize"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize chat"
            aria-valuemin={CHAT_MIN}
            aria-valuemax={CHAT_MAX}
            aria-valuenow={chatWidth}
            tabIndex={0}
            onPointerDown={(e) => beginChatResize(e, chatWidth, setChatWidth)}
            onDoubleClick={() => setChatWidth(CHAT_DEFAULT)}
            onKeyDown={(e) => onChatResizeKey(e, setChatWidth)}
          />
          <ChatPanel
            key={data?.ticker ?? "none"}
            ticker={data?.ticker ?? null}
            onClose={() => setChatOpen(false)}
          />
        </aside>
      </div>
    </div>
  );
}

function formatPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function chatWidthBounds(): { min: number; max: number } {
  const max = Math.min(CHAT_MAX, Math.max(CHAT_MIN, Math.floor(window.innerWidth * 0.62)));
  return { min: CHAT_MIN, max };
}

function clampChatWidth(value: number): number {
  const { min, max } = chatWidthBounds();
  return Math.round(Math.min(max, Math.max(min, value)));
}

function beginChatResize(
  e: React.PointerEvent<HTMLElement>,
  startWidth: number,
  setWidth: (width: number) => void
) {
  if (e.button !== 0) return;
  e.preventDefault();
  const handle = e.currentTarget;
  handle.setPointerCapture(e.pointerId);
  const startX = e.clientX;
  document.body.classList.add("is-resizing-chat");

  const onMove = (ev: PointerEvent) => {
    setWidth(clampChatWidth(startWidth + (startX - ev.clientX)));
  };
  const onUp = () => {
    document.body.classList.remove("is-resizing-chat");
    handle.removeEventListener("pointermove", onMove);
    handle.removeEventListener("pointerup", onUp);
    handle.removeEventListener("pointercancel", onUp);
  };
  handle.addEventListener("pointermove", onMove);
  handle.addEventListener("pointerup", onUp);
  handle.addEventListener("pointercancel", onUp);
}

function onChatResizeKey(e: React.KeyboardEvent<HTMLElement>, setWidth: (updater: (width: number) => number) => void) {
  const step = e.shiftKey ? 48 : 16;
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    setWidth((width) => clampChatWidth(width + step));
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    setWidth((width) => clampChatWidth(width - step));
  } else if (e.key === "Home") {
    e.preventDefault();
    setWidth(() => chatWidthBounds().min);
  } else if (e.key === "End") {
    e.preventDefault();
    setWidth(() => chatWidthBounds().max);
  }
}

function readStoredFlag(key: string, fallback: boolean): boolean {
  try {
    const value = localStorage.getItem(key);
    if (value === "0") return false;
    if (value === "1") return true;
  } catch {
    /* private mode / disabled storage */
  }
  return fallback;
}

function readStoredNumber(key: string, fallback: number, min: number, max: number): number {
  try {
    const value = Number(localStorage.getItem(key));
    if (Number.isFinite(value) && value >= min && value <= max) return value;
  } catch {
    /* private mode / disabled storage */
  }
  return fallback;
}

function writeStored(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode / disabled storage */
  }
}

function ChatIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M3.2 3.2h9.6A1.2 1.2 0 0 1 14 4.4v6.2a1.2 1.2 0 0 1-1.2 1.2H8.1L5 13.9V11.8H3.2A1.2 1.2 0 0 1 2 10.6V4.4a1.2 1.2 0 0 1 1.2-1.2Z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}
