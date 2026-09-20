import { useEffect, useRef, useState } from "react";
import { fetchChatModels, sendChat } from "../api";
import type { ChatMessage, ChatModelOption } from "../types";
import ChatMarkdown from "./ChatMarkdown";

const DEFAULT_MODEL = "deepseek/deepseek-v4.1-flash";

const SUGGESTIONS = [
  "What drove the biggest move?",
  "Summarize the up days versus the down days.",
  "Which session had the largest drop?",
];

interface Props {
  ticker: string | null;
  onClose?: () => void;
}

export default function ChatPanel({ ticker, onClose }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<ChatModelOption[]>([]);
  const [model, setModel] = useState(DEFAULT_MODEL);
  const endRef = useRef<HTMLDivElement>(null);
  const canAsk = Boolean(ticker);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, loading]);

  useEffect(() => {
    let cancelled = false;
    fetchChatModels()
      .then((rows) => {
        if (cancelled) return;
        setModels(rows);
        if (rows.some((row) => row.id === DEFAULT_MODEL)) {
          setModel(DEFAULT_MODEL);
        } else if (rows.length > 0) {
          setModel((prev) => (rows.some((row) => row.id === prev) ? prev : rows[0].id));
        }
      })
      .catch(() => {
        /* selector stays empty; backend falls back to its default model */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setMessages([]);
    setInput("");
  }, [ticker]);

  async function ask(text: string) {
    if (!ticker || !text || loading) return;
    const history = messages;
    const next: ChatMessage[] = [...history, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const { reply } = await sendChat({
        ticker,
        message: text,
        history,
        model: model || undefined,
      });
      setMessages([...next, { role: "assistant", content: reply }]);
    } catch (err) {
      setMessages([...next, { role: "assistant", content: `Error: ${(err as Error).message}` }]);
    } finally {
      setLoading(false);
    }
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    void ask(input.trim());
  }

  function onComposerKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void ask(input.trim());
    }
  }

  return (
    <div className="chat">
      <div className="chat-head">
        <div className="chat-head-row">
          <h2>Chat</h2>
          {onClose && (
            <button type="button" className="ghost-btn" onClick={onClose} aria-label="Hide chat">
              <span aria-hidden="true">✕</span>
            </button>
          )}
        </div>
        <p className="muted">
          {ticker ? `Ask anything about ${ticker}` : "Select a ticker to start a conversation"}
        </p>
      </div>
      <div className="chat-log">
        {messages.length === 0 && (
          <div className="chat-empty">
            {ticker
              ? `Chat can look up ${ticker}’s 2% move days, any session in the window, and news when it needs them.`
              : "Search a seeded ticker first."}
            {ticker && (
              <div className="suggestions">
                {SUGGESTIONS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    className="suggestion"
                    disabled={loading}
                    onClick={() => void ask(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {messages.map((m, i) => (
          <div key={`${m.role}-${i}`} className={`bubble ${m.role}`}>
            {m.role === "assistant" && !m.content.startsWith("Error:") ? (
              <ChatMarkdown text={m.content} />
            ) : (
              m.content
            )}
          </div>
        ))}
        {loading && <div className="bubble assistant muted">Thinking…</div>}
        <div ref={endRef} />
      </div>
      <div className="chat-composer">
        <form className="composer-card" onSubmit={submit}>
          <textarea
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onComposerKeyDown}
            placeholder={disabledPlaceholder(ticker)}
            disabled={!canAsk || loading}
          />
          <div className="composer-toolbar">
            {models.length > 0 ? (
              <label className="model-chip">
                <span className="visually-hidden">Model</span>
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={loading}
                  aria-label="Chat model"
                  title={models.find((m) => m.id === model)?.label || "Chat model"}
                >
                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.short || m.label}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <span />
            )}
            <button
              className="icon-btn"
              type="submit"
              disabled={!canAsk || loading || !input.trim()}
              aria-label="Send"
            >
              ↑
            </button>
          </div>
        </form>
        <p className="chat-disclaimer">
          Volatility Tracker is an AI and can make mistakes. Check important info. This is not investment advice.
        </p>
      </div>
    </div>
  );
}

function disabledPlaceholder(ticker: string | null): string {
  if (!ticker) return "Select a ticker to chat";
  return "Ask a question";
}
