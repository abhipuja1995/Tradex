"use client";

import { useEffect, useState, useCallback } from "react";

type WalletData = {
  total_balance: number;
  available_balance: number;
  locked_in_trades: number;
  daily_invested: number;
  daily_pnl: number;
  trade_date: string;
};

type Trade = {
  id: string;
  symbol: string;
  direction: string;
  quantity: number;
  entry_price: number;
  exit_price: number | null;
  stop_loss_price: number;
  target_price: number;
  status: string;
  pnl: number | null;
  pnl_percent: number | null;
  entry_time: string;
  strategy: string;
  rsi_at_entry: number | null;
  ai_signal: string | null;
  ai_confidence: number | null;
  paper_trade: boolean;
};

type BotStatus = {
  state: string;
  paper_trading: boolean;
  market_open: boolean;
  wallet: {
    total_balance: number;
    daily_invested: number;
    daily_pnl: number;
    remaining_cap: number;
  } | null;
};

type DailyPerf = {
  trade_date: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_pnl: number;
  pnl_percent: number;
};

export default function TradingDashboard() {
  const [wallet, setWallet] = useState<WalletData | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null);
  const [performance, setPerformance] = useState<DailyPerf[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [walletRes, tradesRes, botRes, perfRes] = await Promise.all([
        fetch("/api/trading/wallet"),
        fetch(
          `/api/trading/trades?date=${new Date().toISOString().split("T")[0]}`
        ),
        fetch("/api/trading/bot"),
        fetch("/api/trading/performance?days=7"),
      ]);

      const walletData = await walletRes.json();
      const tradesData = await tradesRes.json();
      const botData = await botRes.json();
      const perfData = await perfRes.json();

      setWallet(walletData.wallet);
      setTrades(tradesData.trades || []);
      setBotStatus(botData);
      setPerformance(perfData.performance || []);
    } catch (e) {
      console.error("Failed to fetch data:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const controlBot = async (action: string) => {
    await fetch("/api/trading/bot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    });
    fetchData();
  };

  const openTrades = trades.filter((t) => t.status === "OPEN");
  const closedTrades = trades.filter((t) => t.status !== "OPEN");

  if (loading) {
    return (
      <div
        className="container"
        style={{ textAlign: "center", paddingTop: "6rem" }}
      >
        <div className="title" style={{ marginBottom: "1rem" }}>
          TradeX
        </div>
        <div style={{ color: "var(--text-secondary)" }}>
          Loading dashboard...
        </div>
      </div>
    );
  }

  return (
    <div className="container">
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1.5rem",
        }}
      >
        <div>
          <h1 className="title" style={{ marginBottom: "0.25rem" }}>
            Dashboard
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
            Automated micro-trading with AI-powered signals
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <StatusBadge state={botStatus?.state || "OFFLINE"} />
          {botStatus?.paper_trading && (
            <span
              style={{
                background: "rgba(234, 179, 8, 0.15)",
                color: "#eab308",
                padding: "0.2rem 0.6rem",
                borderRadius: "6px",
                fontSize: "0.7rem",
                fontWeight: 600,
                letterSpacing: "0.05em",
              }}
            >
              PAPER
            </span>
          )}
        </div>
      </div>

      {/* Stats Row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 220px",
          gap: "1rem",
          marginBottom: "1.5rem",
        }}
      >
        <StatCard
          label="Wallet Balance"
          value={`\u20B9${(wallet?.total_balance || 0).toFixed(2)}`}
        />
        <StatCard
          label="Daily Invested"
          value={`\u20B9${(wallet?.daily_invested || 0).toFixed(2)}`}
          sub="of \u20B9840 cap"
          progress={((wallet?.daily_invested || 0) / 840) * 100}
        />
        <StatCard
          label="Daily P&L"
          value={`\u20B9${(wallet?.daily_pnl || 0).toFixed(2)}`}
          color={
            (wallet?.daily_pnl || 0) >= 0 ? "var(--success)" : "var(--danger)"
          }
        />
        <div
          className="glass-panel"
          style={{
            padding: "1rem",
            display: "flex",
            flexDirection: "column",
            gap: "0.4rem",
          }}
        >
          <div
            style={{
              fontSize: "0.7rem",
              color: "var(--text-secondary)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: "0.2rem",
            }}
          >
            Bot Controls
          </div>
          <button
            className="btn"
            style={{ background: "var(--success)" }}
            onClick={() => controlBot("start")}
          >
            Start
          </button>
          <button
            className="btn"
            style={{ background: "var(--warning)", color: "#000" }}
            onClick={() => controlBot("pause")}
          >
            Pause
          </button>
          <button
            className="btn"
            style={{ background: "var(--danger)" }}
            onClick={() => controlBot("stop")}
          >
            Stop
          </button>
        </div>
      </div>

      {/* Active Trades */}
      <div
        className="glass-panel"
        style={{ padding: "1.25rem", marginBottom: "1.5rem" }}
      >
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
          Active Trades
          <span
            style={{
              background: "rgba(34,197,94,0.15)",
              color: "var(--success)",
              padding: "0.1rem 0.5rem",
              borderRadius: 4,
              fontSize: "0.7rem",
            }}
          >
            {openTrades.length}
          </span>
        </h2>
        {openTrades.length === 0 ? (
          <p
            style={{
              color: "var(--text-secondary)",
              fontSize: "0.85rem",
              padding: "1rem 0",
            }}
          >
            No active positions
          </p>
        ) : (
          <TradeTable trades={openTrades} showPnl={false} />
        )}
      </div>

      {/* Bottom Row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "1.5rem",
        }}
      >
        <div className="glass-panel" style={{ padding: "1.25rem" }}>
          <h2
            style={{
              fontSize: "0.95rem",
              fontWeight: 600,
              marginBottom: "0.75rem",
            }}
          >
            Today&apos;s Closed ({closedTrades.length})
          </h2>
          {closedTrades.length === 0 ? (
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "0.85rem",
                padding: "1rem 0",
              }}
            >
              No closed trades today
            </p>
          ) : (
            <TradeTable trades={closedTrades} showPnl={true} />
          )}
        </div>

        <div className="glass-panel" style={{ padding: "1.25rem" }}>
          <h2
            style={{
              fontSize: "0.95rem",
              fontWeight: 600,
              marginBottom: "0.75rem",
            }}
          >
            7-Day Performance
          </h2>
          {performance.length === 0 ? (
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "0.85rem",
                padding: "1rem 0",
              }}
            >
              No performance data yet
            </p>
          ) : (
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.8rem",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border-glass)",
                  }}
                >
                  <th style={th}>Date</th>
                  <th style={th}>Trades</th>
                  <th style={th}>W/L</th>
                  <th style={th}>P&L</th>
                </tr>
              </thead>
              <tbody>
                {performance.map((p) => (
                  <tr
                    key={p.trade_date}
                    style={{
                      borderBottom: "1px solid rgba(255,255,255,0.03)",
                    }}
                  >
                    <td style={td}>{p.trade_date}</td>
                    <td style={td}>{p.total_trades}</td>
                    <td style={td}>
                      <span style={{ color: "var(--success)" }}>
                        {p.winning_trades}
                      </span>
                      /
                      <span style={{ color: "var(--danger)" }}>
                        {p.losing_trades}
                      </span>
                    </td>
                    <td
                      style={{
                        ...td,
                        color:
                          p.total_pnl >= 0
                            ? "var(--success)"
                            : "var(--danger)",
                        fontWeight: 600,
                      }}
                    >
                      {"\u20B9"}
                      {p.total_pnl.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ state }: { state: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    RUNNING: { bg: "rgba(34, 197, 94, 0.15)", text: "#22c55e" },
    PAUSED: { bg: "rgba(234, 179, 8, 0.15)", text: "#eab308" },
    STOPPED: { bg: "rgba(239, 68, 68, 0.15)", text: "#ef4444" },
    WAITING_MARKET: { bg: "rgba(59, 130, 246, 0.15)", text: "#3b82f6" },
    OFFLINE: { bg: "rgba(107, 114, 128, 0.15)", text: "#6b7280" },
  };
  const c = colors[state] || colors.OFFLINE;
  return (
    <span
      style={{
        background: c.bg,
        color: c.text,
        padding: "0.2rem 0.6rem",
        borderRadius: "6px",
        fontSize: "0.7rem",
        fontWeight: 600,
        letterSpacing: "0.05em",
      }}
    >
      {state}
    </span>
  );
}

function StatCard({
  label,
  value,
  sub,
  color,
  progress,
}: {
  label: string;
  value: string;
  sub?: string;
  color?: string;
  progress?: number;
}) {
  return (
    <div className="glass-panel" style={{ padding: "1.25rem" }}>
      <div
        style={{
          fontSize: "0.7rem",
          color: "var(--text-secondary)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          marginBottom: "0.5rem",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "1.5rem",
          fontWeight: 700,
          color: color || "var(--text-primary)",
        }}
      >
        {value}
      </div>
      {sub && (
        <div
          style={{
            fontSize: "0.7rem",
            color: "var(--text-secondary)",
            marginTop: "0.25rem",
          }}
        >
          {sub}
        </div>
      )}
      {progress !== undefined && (
        <div
          style={{
            marginTop: "0.5rem",
            height: 3,
            background: "rgba(255,255,255,0.05)",
            borderRadius: 2,
          }}
        >
          <div
            style={{
              height: "100%",
              width: `${Math.min(progress, 100)}%`,
              background:
                progress >= 100 ? "var(--danger)" : "var(--accent)",
              borderRadius: 2,
              transition: "width 0.3s",
            }}
          />
        </div>
      )}
    </div>
  );
}

function TradeTable({
  trades,
  showPnl,
}: {
  trades: Trade[];
  showPnl: boolean;
}) {
  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "0.8rem",
        }}
      >
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
            <th style={th}>Symbol</th>
            <th style={th}>Qty</th>
            <th style={th}>Entry</th>
            {showPnl && <th style={th}>Exit</th>}
            <th style={th}>SL</th>
            <th style={th}>Target</th>
            <th style={th}>RSI</th>
            <th style={th}>AI</th>
            {showPnl && <th style={th}>P&L</th>}
            <th style={th}>Status</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr
              key={t.id}
              style={{
                borderBottom: "1px solid rgba(255,255,255,0.03)",
              }}
            >
              <td style={{ ...td, fontWeight: 600 }}>{t.symbol}</td>
              <td style={td}>{t.quantity}</td>
              <td style={td}>{"\u20B9"}{t.entry_price.toFixed(2)}</td>
              {showPnl && (
                <td style={td}>
                  {t.exit_price
                    ? `\u20B9${t.exit_price.toFixed(2)}`
                    : "-"}
                </td>
              )}
              <td style={td}>{"\u20B9"}{t.stop_loss_price.toFixed(2)}</td>
              <td style={td}>{"\u20B9"}{t.target_price.toFixed(2)}</td>
              <td style={td}>{t.rsi_at_entry?.toFixed(1) || "-"}</td>
              <td style={td}>
                {t.ai_signal && (
                  <span
                    style={{
                      fontSize: "0.65rem",
                      padding: "0.1rem 0.35rem",
                      borderRadius: 4,
                      background:
                        t.ai_signal === "BUY"
                          ? "rgba(34,197,94,0.15)"
                          : "rgba(239,68,68,0.15)",
                      color:
                        t.ai_signal === "BUY" ? "#22c55e" : "#ef4444",
                    }}
                  >
                    {t.ai_signal}{" "}
                    {t.ai_confidence
                      ? `${(t.ai_confidence * 100).toFixed(0)}%`
                      : ""}
                  </span>
                )}
              </td>
              {showPnl && (
                <td
                  style={{
                    ...td,
                    color:
                      (t.pnl || 0) >= 0
                        ? "var(--success)"
                        : "var(--danger)",
                    fontWeight: 600,
                  }}
                >
                  {"\u20B9"}{(t.pnl || 0).toFixed(2)}
                </td>
              )}
              <td style={td}>
                <StatusBadge state={t.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "0.4rem 0.6rem",
  color: "var(--text-secondary)",
  fontWeight: 500,
  fontSize: "0.7rem",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const td: React.CSSProperties = {
  padding: "0.4rem 0.6rem",
  color: "var(--text-primary)",
};
