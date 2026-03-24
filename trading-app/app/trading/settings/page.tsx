"use client";

import { useEffect, useState, useCallback } from "react";

type LearningRule = {
  id: string;
  rule_name: string;
  condition_json: Record<string, any>;
  action: string;
  reason: string;
  is_active: boolean;
  created_at: string;
};

const DEFAULT_WATCHLIST = [
  "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
  "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
  "LT", "AXISBANK", "BAJFINANCE", "MARUTI", "TITAN",
  "SUNPHARMA", "TATAMOTORS", "WIPRO", "HCLTECH", "ADANIENT",
];

const BOT_URL = process.env.NEXT_PUBLIC_TRADING_BOT_URL || "http://localhost:8100";

export default function SettingsPage() {
  const [rules, setRules] = useState<LearningRule[]>([]);
  const [watchlist, setWatchlist] = useState<string[]>(DEFAULT_WATCHLIST);
  const [newSymbol, setNewSymbol] = useState("");
  const [botOnline, setBotOnline] = useState(false);
  const [paperMode, setPaperMode] = useState(true);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [rulesRes, botRes] = await Promise.all([
        fetch("/api/trading/rules"),
        fetch("/api/trading/bot"),
      ]);

      const rulesData = await rulesRes.json();
      const botData = await botRes.json();

      setRules(rulesData.rules || []);
      setBotOnline(botData.state !== "OFFLINE");
      setPaperMode(botData.paper_trading !== false);
    } catch (e) {
      console.error("Failed to fetch:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const toggleRule = async (ruleId: string, isActive: boolean) => {
    await fetch("/api/trading/rules", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rule_id: ruleId, is_active: isActive }),
    });
    setRules((prev) =>
      prev.map((r) => (r.id === ruleId ? { ...r, is_active: isActive } : r))
    );
  };

  const addSymbol = () => {
    const sym = newSymbol.trim().toUpperCase();
    if (sym && !watchlist.includes(sym)) {
      setWatchlist([...watchlist, sym]);
      setNewSymbol("");
    }
  };

  const removeSymbol = (sym: string) => {
    setWatchlist(watchlist.filter((s) => s !== sym));
  };

  const configItems = [
    { label: "Daily Cap", value: "\u20B9840" },
    { label: "Per Trade Cap", value: "\u20B9168" },
    { label: "Max Trades/Day", value: "5" },
    { label: "Stop Loss", value: "1.0%" },
    { label: "Target Profit", value: "1.5%" },
    { label: "Daily Max Loss", value: "3.0%" },
    { label: "Daily Target", value: "5.0%" },
    { label: "RSI Oversold", value: "< 30" },
    { label: "Scan Interval", value: "60s" },
  ];

  if (loading) {
    return (
      <div className="container" style={{ textAlign: "center", paddingTop: "4rem" }}>
        <p style={{ color: "var(--text-secondary)" }}>Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="container" style={{ maxWidth: 900 }}>
      <h1 className="title" style={{ marginBottom: "0.25rem" }}>Settings</h1>
      <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Bot parameters, watchlist, and learning rules
      </p>

      {/* Trading Mode */}
      <div className="glass-panel" style={{ padding: "1.25rem", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          Trading Mode
        </h2>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          <span style={{
            background: paperMode ? "rgba(234,179,8,0.15)" : "rgba(239,68,68,0.15)",
            color: paperMode ? "#eab308" : "#ef4444",
            padding: "0.4rem 0.75rem",
            borderRadius: 6,
            fontWeight: 600,
            fontSize: "0.8rem",
          }}>
            {paperMode ? "PAPER TRADING" : "LIVE TRADING"}
          </span>
          <span style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>
            Bot is {botOnline ? "online" : "offline"}
          </span>
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.7rem", marginTop: "0.5rem" }}>
          Set PAPER_TRADING=false in trading-bot/.env to enable live trading.
        </p>
      </div>

      {/* Risk Parameters */}
      <div className="glass-panel" style={{ padding: "1.25rem", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          Risk Parameters
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.5rem" }}>
          {configItems.map((item) => (
            <div key={item.label} style={{
              padding: "0.6rem",
              background: "rgba(15,23,42,0.5)",
              borderRadius: 6,
            }}>
              <div style={{ fontSize: "0.65rem", color: "var(--text-secondary)", marginBottom: "0.2rem" }}>
                {item.label}
              </div>
              <div style={{ fontSize: "1rem", fontWeight: 600 }}>{item.value}</div>
            </div>
          ))}
        </div>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.7rem", marginTop: "0.5rem" }}>
          Update trading-bot/.env and restart to change parameters.
        </p>
      </div>

      {/* Watchlist */}
      <div className="glass-panel" style={{ padding: "1.25rem", marginBottom: "1rem" }}>
        <h2 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          Watchlist ({watchlist.length})
        </h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginBottom: "0.75rem" }}>
          {watchlist.map((sym) => (
            <span key={sym} style={{
              background: "rgba(59,130,246,0.1)",
              color: "var(--accent)",
              padding: "0.2rem 0.5rem",
              borderRadius: 5,
              fontSize: "0.75rem",
              fontWeight: 500,
              display: "inline-flex",
              alignItems: "center",
              gap: "0.3rem",
            }}>
              {sym}
              <button
                onClick={() => removeSymbol(sym)}
                style={{
                  background: "none", border: "none", color: "var(--danger)",
                  cursor: "pointer", padding: 0, fontSize: "0.8rem", lineHeight: 1,
                }}
              >
                x
              </button>
            </span>
          ))}
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <input
            type="text"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addSymbol()}
            placeholder="Add symbol..."
            style={{
              background: "rgba(15, 23, 42, 0.6)",
              border: "1px solid var(--border-glass)",
              color: "var(--text-primary)",
              padding: "0.4rem 0.75rem",
              borderRadius: 6,
              fontSize: "0.8rem",
              flex: 1,
            }}
          />
          <button className="btn" onClick={addSymbol}>Add</button>
        </div>
      </div>

      {/* Learning Rules */}
      <div className="glass-panel" style={{ padding: "1.25rem" }}>
        <h2 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.75rem" }}>
          Learning Rules ({rules.length})
        </h2>
        {rules.length === 0 ? (
          <p style={{ color: "var(--text-secondary)", fontSize: "0.8rem" }}>
            No rules yet. Auto-generated from end-of-day mistake analysis.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {rules.map((rule) => (
              <div key={rule.id} style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "0.6rem 0.75rem",
                background: "rgba(15,23,42,0.5)",
                borderRadius: 6,
                border: `1px solid ${rule.is_active ? "rgba(34,197,94,0.2)" : "rgba(255,255,255,0.03)"}`,
              }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.85rem" }}>{rule.rule_name}</div>
                  <div style={{ color: "var(--text-secondary)", fontSize: "0.75rem" }}>{rule.reason}</div>
                </div>
                <button
                  onClick={() => toggleRule(rule.id, !rule.is_active)}
                  style={{
                    background: rule.is_active ? "rgba(34,197,94,0.15)" : "rgba(107,114,128,0.15)",
                    color: rule.is_active ? "#22c55e" : "#6b7280",
                    border: "none", padding: "0.3rem 0.6rem", borderRadius: 5,
                    cursor: "pointer", fontSize: "0.7rem", fontWeight: 600,
                  }}
                >
                  {rule.is_active ? "ON" : "OFF"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
