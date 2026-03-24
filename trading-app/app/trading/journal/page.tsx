"use client";

import { useEffect, useState, useCallback } from "react";

type JournalEntry = {
  id: string;
  trade_id: string | null;
  trade_date: string;
  entry_type: string;
  title: string;
  body: string;
  tags: string[];
  created_at: string;
};

type AIDecision = {
  id: string;
  symbol: string;
  decision_date: string;
  signal: string;
  confidence: number;
  final_reasoning: string;
  created_at: string;
};

const TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  TRADE: { bg: "rgba(59, 130, 246, 0.15)", text: "#3b82f6" },
  MISTAKE: { bg: "rgba(239, 68, 68, 0.15)", text: "#ef4444" },
  OBSERVATION: { bg: "rgba(234, 179, 8, 0.15)", text: "#eab308" },
  RULE_CHANGE: { bg: "rgba(139, 92, 246, 0.15)", text: "#8b5cf6" },
};

export default function JournalPage() {
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [aiDecisions, setAiDecisions] = useState<AIDecision[]>([]);
  const [dateFilter, setDateFilter] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [typeFilter, setTypeFilter] = useState("");
  const [tab, setTab] = useState<"journal" | "ai">("journal");
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateFilter) params.set("date", dateFilter);
      if (typeFilter) params.set("type", typeFilter);

      const [journalRes, aiRes] = await Promise.all([
        fetch(`/api/trading/journal?${params}`),
        fetch(`/api/trading/ai-decisions?date=${dateFilter}`),
      ]);

      const journalData = await journalRes.json();
      const aiData = await aiRes.json();

      setEntries(journalData.entries || []);
      setAiDecisions(aiData.decisions || []);
    } catch (e) {
      console.error("Failed to fetch:", e);
    } finally {
      setLoading(false);
    }
  }, [dateFilter, typeFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const inputStyle: React.CSSProperties = {
    background: "rgba(15, 23, 42, 0.6)",
    border: "1px solid var(--border-glass)",
    color: "var(--text-primary)",
    padding: "0.4rem 0.75rem",
    borderRadius: "6px",
    fontSize: "0.8rem",
  };

  return (
    <div className="container" style={{ maxWidth: 960 }}>
      <h1 className="title" style={{ marginBottom: "0.25rem" }}>
        Trade Journal
      </h1>
      <p
        style={{
          color: "var(--text-secondary)",
          fontSize: "0.85rem",
          marginBottom: "1.5rem",
        }}
      >
        Trade logs, AI decisions, and mistake analysis
      </p>

      {/* Filters */}
      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          marginBottom: "1.5rem",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <input
          type="date"
          value={dateFilter}
          onChange={(e) => setDateFilter(e.target.value)}
          style={inputStyle}
        />

        <div
          style={{
            display: "flex",
            gap: 2,
            background: "rgba(15,23,42,0.6)",
            borderRadius: 6,
            padding: 2,
          }}
        >
          {(["journal", "ai"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                padding: "0.35rem 0.75rem",
                borderRadius: 5,
                border: "none",
                background: tab === t ? "var(--accent)" : "transparent",
                color: tab === t ? "white" : "var(--text-secondary)",
                cursor: "pointer",
                fontSize: "0.75rem",
                fontWeight: 500,
              }}
            >
              {t === "journal"
                ? `Journal (${entries.length})`
                : `AI Decisions (${aiDecisions.length})`}
            </button>
          ))}
        </div>

        {tab === "journal" && (
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={inputStyle}
          >
            <option value="">All Types</option>
            <option value="TRADE">Trades</option>
            <option value="MISTAKE">Mistakes</option>
            <option value="OBSERVATION">Observations</option>
            <option value="RULE_CHANGE">Rule Changes</option>
          </select>
        )}
      </div>

      {loading ? (
        <p style={{ color: "var(--text-secondary)", textAlign: "center" }}>
          Loading...
        </p>
      ) : tab === "journal" ? (
        entries.length === 0 ? (
          <div
            className="glass-panel"
            style={{ padding: "3rem", textAlign: "center" }}
          >
            <p style={{ color: "var(--text-secondary)" }}>
              No journal entries for this date
            </p>
          </div>
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "0.6rem",
            }}
          >
            {entries.map((entry) => {
              const colors =
                TYPE_COLORS[entry.entry_type] || TYPE_COLORS.OBSERVATION;
              return (
                <div
                  key={entry.id}
                  className="glass-panel"
                  style={{ padding: "1rem" }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      marginBottom: "0.4rem",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        gap: "0.4rem",
                        alignItems: "center",
                      }}
                    >
                      <span
                        style={{
                          background: colors.bg,
                          color: colors.text,
                          padding: "0.1rem 0.4rem",
                          borderRadius: 4,
                          fontSize: "0.65rem",
                          fontWeight: 600,
                        }}
                      >
                        {entry.entry_type}
                      </span>
                      <h3
                        style={{
                          fontSize: "0.9rem",
                          fontWeight: 600,
                          margin: 0,
                        }}
                      >
                        {entry.title}
                      </h3>
                    </div>
                    <span
                      style={{
                        color: "var(--text-secondary)",
                        fontSize: "0.7rem",
                      }}
                    >
                      {new Date(entry.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "0.8rem",
                      margin: 0,
                      whiteSpace: "pre-line",
                      lineHeight: 1.5,
                    }}
                  >
                    {entry.body}
                  </p>
                  {entry.tags.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        gap: "0.25rem",
                        marginTop: "0.4rem",
                      }}
                    >
                      {entry.tags.map((tag) => (
                        <span
                          key={tag}
                          style={{
                            background: "rgba(255,255,255,0.05)",
                            color: "var(--text-secondary)",
                            padding: "0.1rem 0.35rem",
                            borderRadius: 3,
                            fontSize: "0.6rem",
                          }}
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )
      ) : aiDecisions.length === 0 ? (
        <div
          className="glass-panel"
          style={{ padding: "3rem", textAlign: "center" }}
        >
          <p style={{ color: "var(--text-secondary)" }}>
            No AI decisions for this date
          </p>
        </div>
      ) : (
        <div
          style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}
        >
          {aiDecisions.map((d) => (
            <div
              key={d.id}
              className="glass-panel"
              style={{ padding: "1rem" }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "0.4rem",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    gap: "0.5rem",
                    alignItems: "center",
                  }}
                >
                  <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>
                    {d.symbol}
                  </span>
                  <span
                    style={{
                      background:
                        d.signal === "BUY"
                          ? "rgba(34,197,94,0.15)"
                          : d.signal === "SELL"
                          ? "rgba(239,68,68,0.15)"
                          : "rgba(107,114,128,0.15)",
                      color:
                        d.signal === "BUY"
                          ? "#22c55e"
                          : d.signal === "SELL"
                          ? "#ef4444"
                          : "#6b7280",
                      padding: "0.1rem 0.4rem",
                      borderRadius: 4,
                      fontSize: "0.7rem",
                      fontWeight: 600,
                    }}
                  >
                    {d.signal}
                  </span>
                  <span
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "0.75rem",
                    }}
                  >
                    {(d.confidence * 100).toFixed(0)}% confidence
                  </span>
                </div>
                <span
                  style={{
                    color: "var(--text-secondary)",
                    fontSize: "0.7rem",
                  }}
                >
                  {new Date(d.created_at).toLocaleTimeString()}
                </span>
              </div>
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: "0.8rem",
                  margin: 0,
                  whiteSpace: "pre-line",
                  lineHeight: 1.5,
                  maxHeight: 180,
                  overflow: "auto",
                }}
              >
                {d.final_reasoning || "No reasoning available"}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
