"use client";

import { useEffect, useState, useCallback } from "react";

// ── Types ──────────────────────────────────────────────────────────────────

type StockPick = {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  rsi: number | null;
  trend: string | null;
  signal: "BUY" | "HOLD" | "SELL";
};

type BucketConfig = {
  key: string;
  label: string;
  strategy: string;
  targetIRR: string;
  maxDrawdown: string;
  maxCapPerTrade: string;
  optionsAllocation: string;
  cryptoCap: string;
};

// ── Bucket Definitions ─────────────────────────────────────────────────────

const BUCKETS: BucketConfig[] = [
  {
    key: "weeks",
    label: "Weeks",
    strategy: "Momentum + Options Hedge",
    targetIRR: "20-30%",
    maxDrawdown: "<5%",
    maxCapPerTrade: "5%",
    optionsAllocation: "2%",
    cryptoCap: "10%",
  },
  {
    key: "3m",
    label: "3 Months",
    strategy: "Swing Breakout + Sector Rotation",
    targetIRR: "25-35%",
    maxDrawdown: "<5%",
    maxCapPerTrade: "5%",
    optionsAllocation: "2%",
    cryptoCap: "12%",
  },
  {
    key: "6m",
    label: "6 Months",
    strategy: "Trend Following + Value Accumulation",
    targetIRR: "18-28%",
    maxDrawdown: "<6%",
    maxCapPerTrade: "5%",
    optionsAllocation: "2%",
    cryptoCap: "12%",
  },
  {
    key: "9m",
    label: "9 Months",
    strategy: "Multi-Factor + Dividend Capture",
    targetIRR: "22-30%",
    maxDrawdown: "<7%",
    maxCapPerTrade: "5%",
    optionsAllocation: "2%",
    cryptoCap: "15%",
  },
  {
    key: "12m",
    label: "12 Months",
    strategy: "Core Satellite + Macro Overlay",
    targetIRR: "25-40%",
    maxDrawdown: "<7%",
    maxCapPerTrade: "5%",
    optionsAllocation: "2%",
    cryptoCap: "15%",
  },
];

// ── Shared Styles ──────────────────────────────────────────────────────────

const labelStyle: React.CSSProperties = {
  fontSize: "0.7rem",
  color: "var(--text-secondary)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  marginBottom: "0.35rem",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "0.4rem 0.6rem",
  color: "var(--text-secondary)",
  fontWeight: 500,
  fontSize: "0.7rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const tdStyle: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  color: "var(--text-primary)",
  fontSize: "0.8rem",
};

const gradientBorders: Record<string, string> = {
  weeks: "linear-gradient(135deg, #3b82f6, #22c55e)",
  "3m": "linear-gradient(135deg, #8b5cf6, #3b82f6)",
  "6m": "linear-gradient(135deg, #22c55e, #eab308)",
  "9m": "linear-gradient(135deg, #f97316, #ef4444)",
  "12m": "linear-gradient(135deg, #ec4899, #8b5cf6)",
};

// ── Helpers ────────────────────────────────────────────────────────────────

function changeColor(v: number) {
  return v > 0 ? "var(--success)" : v < 0 ? "var(--danger)" : "var(--text-secondary)";
}

function arrow(v: number) {
  return v > 0 ? "↑" : v < 0 ? "↓" : "–";
}

function signalBadge(signal: string): { bg: string; color: string } {
  if (signal === "BUY") return { bg: "rgba(34,197,94,0.15)", color: "#22c55e" };
  if (signal === "SELL") return { bg: "rgba(239,68,68,0.15)", color: "#ef4444" };
  return { bg: "rgba(234,179,8,0.12)", color: "#eab308" };
}

function deriveSignal(trend: string | null, rsi: number | null): "BUY" | "HOLD" | "SELL" {
  if (!trend && rsi == null) return "HOLD";
  const isBullTrend = trend?.includes("BULL");
  const isBearTrend = trend?.includes("BEAR");
  const isOversold = rsi != null && rsi < 35;
  const isOverbought = rsi != null && rsi > 70;

  if (isBullTrend && !isOverbought) return "BUY";
  if (isOversold && !isBearTrend) return "BUY";
  if (isBearTrend && isOverbought) return "SELL";
  if (isBearTrend) return "SELL";
  return "HOLD";
}

function trendLabel(trend: string | null): string {
  if (!trend) return "–";
  if (trend.includes("BULL")) return "ABOVE";
  if (trend.includes("BEAR")) return "BELOW";
  return "NEUTRAL";
}

function trendColor(trend: string | null): string {
  if (!trend) return "var(--text-secondary)";
  if (trend.includes("BULL")) return "var(--success)";
  if (trend.includes("BEAR")) return "var(--danger)";
  return "var(--text-secondary)";
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function InvestmentsPage() {
  const [activeBucket, setActiveBucket] = useState("weeks");
  const [stocks, setStocks] = useState<StockPick[]>([]);
  const [loading, setLoading] = useState(true);
  const [killSwitchActive, setKillSwitchActive] = useState(true);

  const bucket = BUCKETS.find((b) => b.key === activeBucket)!;

  const fetchStocks = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/market/indices");
      const data = await res.json();
      // Map indices data (QuoteData + technicals) to stock pick format
      const indexItems = data.indices || [];
      const picks: StockPick[] = indexItems.map((item: Record<string, unknown>) => {
        const trend = (item.trend as string) || null;
        const rsi = item.rsi != null ? (item.rsi as number) : null;
        return {
          symbol: (item.symbol as string) || "",
          name: (item.name as string) || (item.symbol as string) || "",
          price: (item.price as number) || 0,
          changePercent: (item.changePercent as number) || 0,
          rsi,
          trend,
          signal: deriveSignal(trend, rsi),
        };
      });
      setStocks(picks);
    } catch {
      setStocks([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStocks();
    const interval = setInterval(fetchStocks, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchStocks]);

  return (
    <div className="container">
      {/* Header */}
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 className="title" style={{ marginBottom: "0.25rem" }}>
          Investments
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
          Short-term investment engine with time-bucketed strategies
        </p>
      </div>

      {/* Time Bucket Tabs */}
      <div
        style={{
          display: "flex",
          gap: "0.25rem",
          marginBottom: "1.5rem",
          borderBottom: "1px solid var(--border-glass)",
        }}
      >
        {BUCKETS.map((b) => (
          <button
            key={b.key}
            onClick={() => setActiveBucket(b.key)}
            style={{
              background: activeBucket === b.key ? "var(--bg-card)" : "transparent",
              color: activeBucket === b.key ? "var(--text-primary)" : "var(--text-secondary)",
              border:
                activeBucket === b.key
                  ? "1px solid var(--border-glass)"
                  : "1px solid transparent",
              borderBottom:
                activeBucket === b.key ? "1px solid var(--bg-dark)" : "1px solid transparent",
              padding: "0.55rem 1.1rem",
              borderRadius: "8px 8px 0 0",
              fontSize: "0.82rem",
              fontWeight: activeBucket === b.key ? 600 : 400,
              cursor: "pointer",
              transition: "all 0.15s",
              marginBottom: "-1px",
            }}
          >
            {b.label}
          </button>
        ))}
      </div>

      {/* Strategy Card with gradient border */}
      <div
        style={{
          padding: "2px",
          borderRadius: "14px",
          background: gradientBorders[activeBucket] || gradientBorders.weeks,
          marginBottom: "1.25rem",
        }}
      >
        <div
          className="glass-panel"
          style={{
            padding: "1.25rem 1.5rem",
            borderRadius: "12px",
            display: "grid",
            gridTemplateColumns: "1fr auto auto",
            gap: "2rem",
            alignItems: "center",
          }}
        >
          <div>
            <div style={labelStyle}>Strategy</div>
            <div style={{ fontSize: "1.15rem", fontWeight: 700 }}>{bucket.strategy}</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={labelStyle}>Target IRR</div>
            <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "var(--success)" }}>
              {bucket.targetIRR}
            </div>
          </div>
          <div style={{ textAlign: "center" }}>
            <div style={labelStyle}>Max Drawdown</div>
            <div style={{ fontSize: "1.3rem", fontWeight: 700, color: "var(--danger)" }}>
              {bucket.maxDrawdown}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "1.25rem" }}>
        {/* Stock Picks Table */}
        <div className="glass-panel" style={{ padding: "1.25rem" }}>
          <h2
            style={{
              fontSize: "0.95rem",
              fontWeight: 600,
              marginBottom: "0.75rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            Stock Picks
            <span
              style={{
                background: "rgba(59,130,246,0.15)",
                color: "var(--accent)",
                padding: "0.1rem 0.5rem",
                borderRadius: 4,
                fontSize: "0.7rem",
              }}
            >
              {stocks.length}
            </span>
          </h2>

          {loading ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
              Loading...
            </div>
          ) : stocks.length === 0 ? (
            <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
              No stock picks available
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                    <th style={thStyle}>Symbol</th>
                    <th style={thStyle}>Price</th>
                    <th style={thStyle}>Change%</th>
                    <th style={thStyle}>RSI</th>
                    <th style={thStyle}>DMA Trend</th>
                    <th style={thStyle}>Signal</th>
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((s) => {
                    const sig = signalBadge(s.signal);
                    return (
                      <tr key={s.symbol} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                        <td style={{ ...tdStyle, fontWeight: 600 }}>{s.name || s.symbol}</td>
                        <td style={tdStyle}>
                          {s.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                        </td>
                        <td style={{ ...tdStyle, color: changeColor(s.changePercent), fontWeight: 600 }}>
                          {arrow(s.changePercent)} {s.changePercent > 0 ? "+" : ""}
                          {s.changePercent.toFixed(2)}%
                        </td>
                        <td
                          style={{
                            ...tdStyle,
                            color:
                              s.rsi != null && s.rsi > 70
                                ? "var(--danger)"
                                : s.rsi != null && s.rsi < 30
                                ? "var(--success)"
                                : "var(--text-primary)",
                          }}
                        >
                          {s.rsi != null ? s.rsi.toFixed(1) : "–"}
                        </td>
                        <td style={tdStyle}>
                          <span
                            style={{
                              color: trendColor(s.trend),
                              fontWeight: 600,
                              fontSize: "0.75rem",
                            }}
                          >
                            {trendLabel(s.trend)}
                          </span>
                        </td>
                        <td style={tdStyle}>
                          <span
                            style={{
                              background: sig.bg,
                              color: sig.color,
                              padding: "0.12rem 0.45rem",
                              borderRadius: "4px",
                              fontSize: "0.68rem",
                              fontWeight: 600,
                            }}
                          >
                            {s.signal}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right Sidebar */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
          {/* Risk Rules */}
          <div className="glass-panel" style={{ padding: "1.25rem" }}>
            <h2 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
              Risk Rules
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
              <RuleRow label="Max capital per trade" value={bucket.maxCapPerTrade} />
              <RuleRow label="Options allocation" value={bucket.optionsAllocation} />
              <RuleRow label="Crypto cap" value={bucket.cryptoCap} />
            </div>
          </div>

          {/* Portfolio Rules */}
          <div className="glass-panel" style={{ padding: "1.25rem" }}>
            <h2 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
              Portfolio Philosophy
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <PhilosophyBar label="Systematic" sublabel="Signals + Models" pct={70} color="var(--accent)" />
              <PhilosophyBar label="Discretionary" sublabel="Macro Overlays" pct={30} color="var(--purple)" />
            </div>
          </div>

          {/* Kill Switch */}
          <div className="glass-panel" style={{ padding: "1.25rem" }}>
            <h2
              style={{
                fontSize: "0.95rem",
                fontWeight: 600,
                marginBottom: "0.75rem",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              Kill Switch
              <span
                style={{
                  background: killSwitchActive ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
                  color: killSwitchActive ? "#22c55e" : "#ef4444",
                  padding: "0.12rem 0.5rem",
                  borderRadius: "4px",
                  fontSize: "0.68rem",
                  fontWeight: 600,
                }}
              >
                {killSwitchActive ? "ACTIVE" : "INACTIVE"}
              </span>
            </h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem", marginBottom: "0.75rem" }}>
              If portfolio drawdown exceeds 10%, all trading will stop automatically.
            </p>
            <button
              className="btn"
              onClick={() => setKillSwitchActive((prev) => !prev)}
              style={{
                width: "100%",
                background: killSwitchActive ? "var(--danger)" : "var(--success)",
                fontSize: "0.8rem",
              }}
            >
              {killSwitchActive ? "Deactivate Kill Switch" : "Activate Kill Switch"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sub Components ─────────────────────────────────────────────────────────

function RuleRow({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>{label}</span>
      <span
        style={{
          fontSize: "0.82rem",
          fontWeight: 600,
          color: "var(--text-primary)",
          background: "rgba(255,255,255,0.04)",
          padding: "0.15rem 0.5rem",
          borderRadius: "4px",
        }}
      >
        {value}
      </span>
    </div>
  );
}

function PhilosophyBar({
  label,
  sublabel,
  pct,
  color,
}: {
  label: string;
  sublabel: string;
  pct: number;
  color: string;
}) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
        <div>
          <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>{label}</span>
          <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", marginLeft: "0.4rem" }}>
            {sublabel}
          </span>
        </div>
        <span style={{ fontSize: "0.82rem", fontWeight: 700, color }}>{pct}%</span>
      </div>
      <div
        style={{
          height: "6px",
          background: "rgba(255,255,255,0.06)",
          borderRadius: "3px",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: color,
            borderRadius: "3px",
            transition: "width 0.3s",
          }}
        />
      </div>
    </div>
  );
}
