import type { ChatMessage, ChatModelOption, TickerResponse, TickerSummary } from "./types";

async function handle<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export async function fetchTickers(): Promise<TickerSummary[]> {
  const resp = await fetch("/api/tickers");
  return handle<TickerSummary[]>(resp);
}

export async function fetchTicker(ticker: string): Promise<TickerResponse> {
  const resp = await fetch(`/api/tickers/${encodeURIComponent(ticker)}`);
  return handle<TickerResponse>(resp);
}

export async function fetchMoveNews(ticker: string, date: string): Promise<TickerResponse> {
  const params = new URLSearchParams({
    include_news: "true",
    start: date,
    end: date,
  });
  const resp = await fetch(`/api/tickers/${encodeURIComponent(ticker)}?${params}`);
  return handle<TickerResponse>(resp);
}

export interface ChatParams {
  ticker: string;
  message: string;
  history: ChatMessage[];
  model?: string;
}

export async function fetchChatModels(): Promise<ChatModelOption[]> {
  const resp = await fetch("/api/chat/models");
  return handle<ChatModelOption[]>(resp);
}

export interface ChatStreamHandlers {
  onStatus?: (message: string) => void;
  onToken?: (text: string) => void;
  onDone?: (info: { grounded: boolean; model: string | null }) => void;
}

export async function streamChat(p: ChatParams, handlers: ChatStreamHandlers): Promise<void> {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(p),
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* ignore non-JSON error bodies */
    }
    throw new Error(detail);
  }
  if (!resp.body) {
    throw new Error("Chat stream was empty.");
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawDone = false;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const parsed = parseSseChunk(chunk);
      if (!parsed) continue;
      if (parsed.event === "status" && parsed.data.message) {
        handlers.onStatus?.(String(parsed.data.message));
      } else if (parsed.event === "token" && parsed.data.text) {
        handlers.onToken?.(String(parsed.data.text));
      } else if (parsed.event === "done") {
        sawDone = true;
        handlers.onDone?.({
          grounded: Boolean(parsed.data.grounded),
          model: typeof parsed.data.model === "string" ? parsed.data.model : null,
        });
      } else if (parsed.event === "error" && parsed.data.message) {
        throw new Error(String(parsed.data.message));
      }
    }
  }
  if (!sawDone) {
    handlers.onDone?.({ grounded: true, model: null });
  }
}

function parseSseChunk(chunk: string): { event: string; data: Record<string, unknown> } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of chunk.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    return { event, data };
  } catch {
    return null;
  }
}
