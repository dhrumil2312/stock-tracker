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

export async function sendChat(
  p: ChatParams
): Promise<{ reply: string; grounded: boolean; model: string | null }> {
  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
  });
  return handle<{ reply: string; grounded: boolean; model: string | null }>(resp);
}
