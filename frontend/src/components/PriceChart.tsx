import {
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Movement, PricePoint } from "../types";

interface Props {
  prices: PricePoint[];
  movements: Movement[];
  selected: string | null;
  onSelectMovement: (date: string) => void;
}

interface ChartRow extends PricePoint {
  prevClose: number | null;
}

export default function PriceChart({ prices, movements, selected, onSelectMovement }: Props) {
  const moveByDate = new Map(movements.map((m) => [m.date, m]));
  const rows: ChartRow[] = prices.map((p, i) => ({
    ...p,
    prevClose: i > 0 ? prices[i - 1].close : null,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={rows} margin={{ top: 12, right: 16, bottom: 8, left: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#5f6368" }} minTickGap={40} axisLine={false} tickLine={false} />
        <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11, fill: "#5f6368" }} width={54} axisLine={false} tickLine={false} />
        <Tooltip content={<ChartTooltip />} />
        <Line
          type="monotone"
          dataKey="close"
          name="Close"
          stroke="#1a73e8"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        {rows.map((p) => {
          const m = moveByDate.get(p.date);
          if (!m) return null;
          const featured = selected === p.date;
          return (
            <ReferenceDot
              key={p.date}
              x={p.date}
              y={p.close}
              r={featured ? 8 : 5}
              fill={m.direction === "up" ? "#137333" : "#c5221f"}
              stroke={featured ? "#1a73e8" : "#fff"}
              strokeWidth={featured ? 2 : 1}
              onClick={() => onSelectMovement(p.date)}
              style={{ cursor: "pointer" }}
            />
          );
        })}
      </LineChart>
    </ResponsiveContainer>
  );
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartRow }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-date">{label}</div>
      <div className="chart-tooltip-row">
        <span>Open</span>
        <strong>{formatPrice(row.open)}</strong>
      </div>
      <div className="chart-tooltip-row">
        <span>High</span>
        <strong>{formatPrice(row.high)}</strong>
      </div>
      <div className="chart-tooltip-row">
        <span>Low</span>
        <strong>{formatPrice(row.low)}</strong>
      </div>
      <div className="chart-tooltip-row">
        <span>Close</span>
        <strong>{formatPrice(row.close)}</strong>
      </div>
      <div className="chart-tooltip-row">
        <span>Prev close</span>
        <strong>{formatPrice(row.prevClose)}</strong>
      </div>
      {row.pct_change != null && (
        <div className={`chart-tooltip-change ${row.pct_change >= 0 ? "up" : "down"}`}>
          {row.pct_change > 0 ? "+" : ""}
          {row.pct_change.toFixed(2)}% vs prior close
        </div>
      )}
    </div>
  );
}

function formatPrice(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
