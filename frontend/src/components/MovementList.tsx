import type { Movement, NewsCategory } from "../types";

const CATEGORY_LABEL: Record<NewsCategory, string> = {
  company: "Company",
  industry: "Industry",
  macro: "Macro",
  unknown: "Other",
};

interface Props {
  movements: Movement[];
  selected: string | null;
  newsLoading: boolean;
  newsError: string | null;
  onLoadNews: (date: string) => void;
}

export default function MovementList({
  movements,
  selected,
  newsLoading,
  newsError,
  onLoadNews,
}: Props) {
  if (movements.length === 0) {
    return <p className="muted">No days with a move of 2% or more in the latest scan.</p>;
  }

  return (
    <div className="movement-list">
      {movements.map((m) => {
        const featured = selected === m.date;
        return (
          <div key={m.date} className={`movement-card${featured ? " featured" : ""}`}>
            <div className="movement-row">
              <div className="movement-id">
                <span className="movement-date">{formatDay(m.date)}</span>
                <span className={`pill ${m.direction}`}>
                  {m.pct_change > 0 ? "+" : ""}
                  {m.pct_change.toFixed(2)}%
                </span>
              </div>
              <dl className="ohlcv-stats">
                <div>
                  <dt>Open</dt>
                  <dd>{formatPrice(m.open)}</dd>
                </div>
                <div>
                  <dt>High</dt>
                  <dd>{formatPrice(m.high)}</dd>
                </div>
                <div>
                  <dt>Low</dt>
                  <dd>{formatPrice(m.low)}</dd>
                </div>
                <div>
                  <dt>Close</dt>
                  <dd>{formatPrice(m.close)}</dd>
                </div>
                <div>
                  <dt>Vol</dt>
                  <dd>{formatVolume(m.volume)}</dd>
                </div>
              </dl>
              <button
                type="button"
                className={`day-chat-btn${featured ? " is-active" : ""}`}
                disabled={featured && newsLoading}
                onClick={() => onLoadNews(m.date)}
              >
                {featured && newsLoading ? "Loading…" : featured ? "News" : "Load news"}
              </button>
            </div>

            {featured && (
              <div className="day-panel">
                {newsLoading && (
                  <div className="news-loading" aria-live="polite">
                    <p className="muted">Finding news for {formatDay(m.date)}…</p>
                    <div className="skeleton" />
                    <div className="skeleton" />
                    <div className="skeleton short" />
                  </div>
                )}
                {!newsLoading && newsError && <p className="news-error">{newsError}</p>}
                {!newsLoading && !newsError && m.articles.length === 0 && (
                  <p className="muted">No news found for this day.</p>
                )}
                {!newsLoading && !newsError && m.articles.length > 0 && (
                  <ul className="article-list">
                    {m.articles.slice(0, 5).map((a) => (
                      <li key={a.url}>
                        <span className={`cat cat-${a.category}`}>{CATEGORY_LABEL[a.category]}</span>
                        <a href={a.url} target="_blank" rel="noreferrer">
                          {a.title}
                        </a>
                        {a.source && <span className="article-source">{a.source}</span>}
                        {a.snippet && <p className="snippet">{a.snippet}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function formatDay(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function formatPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString();
}
