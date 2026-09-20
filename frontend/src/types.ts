export interface PricePoint {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  adj_close: number | null;
  volume: number;
  pct_change: number | null;
}

export type NewsCategory = "company" | "industry" | "macro" | "unknown";

export interface Article {
  title: string;
  url: string;
  source: string | null;
  published_at: string | null;
  snippet: string | null;
  category: NewsCategory;
}

export interface Movement {
  date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number;
  adj_close: number | null;
  prev_adj_close: number | null;
  volume: number | null;
  pct_change: number;
  direction: "up" | "down";
  articles: Article[];
}

export interface TickerSummary {
  ticker: string;
  name: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
}

export interface TickerResponse {
  ticker: string;
  threshold: number;
  currency: string | null;
  company_name: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  prices: PricePoint[];
  movements: Movement[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatModelOption {
  id: string;
  label: string;
  short?: string | null;
}
