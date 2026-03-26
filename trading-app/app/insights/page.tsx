"use client";

import { useEffect, useState, useCallback } from "react";

// ── Types (aligned with actual API responses) ───────────────────────────────

type MacroSignal = {
  name: string;
  value: number;
  signal: "BULLISH" | "BEARISH" | "NEUTRAL";
  description: string;
};

type MacroData = {
  regime: "RISK_ON" | "RISK_OFF" | "TRANSITION";
  signals: MacroSignal[];
};

type IndexData = {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  dma50: number | null;
  dma100: number | null;
  dma200: number | null;
  trend: string | null;
  rsi: number | null;
};

type BreadthData = {
  dma200: { above: number; total: number; percent: number };
  dma50: { above: number; total: number; percent: number };
  health: "STRONG" | "MODERATE" | "WEAK";
};

type VolatilityData = {
  indiaVix: { price: number; level: string; signal: string; description: string } | null;
  usVix: { price: number; level: string; signal: string; description: string } | null;
};

type CommodityItem = {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
  trend: string | null;
  rsi: number | null;
};

type CryptoItem = {
  symbol: string;
  name: string;
  price: number;
  changePercent: number;
};

// ── Tabs ───────────────────────────────────────────────────────────────────

type TabKey = "macro" | "health" | "volatility" | "commodities" | "crypto";

const TABS: { key: TabKey; label: string }[] = [
  { key: "macro", label: "Macro" },
  { key: "health", label: "Market Health" },
  { key: "volatility", label: "Volatility" },
  { key: "commodities", label: "Commodities" },
  { key: "crypto", label: "Crypto" },
];

// ── Shared Styles ──────────────────────────────────────────────────────────

const cardGrid3: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
  gap: "1rem",
};

const cardGrid4: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
  gap: "1rem",
};

const labelStyle: React.CSSProperties = {
  fontSize: "0.7rem",
  color: "var(--text-secondary)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  marginBottom: "0.35rem",
};

const bigNum: React.CSSProperties = {
  fontSize: "1.6rem",
  fontWeight: 700,
};

const smallBadge = (bg: string, color: string): React.CSSProperties => ({
  display: "inline-block",
  background: bg,
  color,
  padding: "0.15rem 0.55rem",
  borderRadius: "6px",
  fontSize: "0.7rem",
  fontWeight: 600,
  letterSpacing: "0.04em",
});

// ── Helpers ────────────────────────────────────────────────────────────────

function changeColor(v: number) {
  return v > 0 ? "var(--success)" : v < 0 ? "var(--danger)" : "var(--text-secondary)";
}

function arrow(v: number) {
  return v > 0 ? "↑" : v < 0 ? "↓" : "–";
}

function signalColor(d: string) {
  const lower = d.toLowerCase();
  if (lower === "bullish") return "var(--success)";
  if (lower === "bearish") return "var(--danger)";
  return "var(--text-secondary)";
}

function regimeLabel(regime: string): string {
  return regime.replace(/_/g, " ");
}

function vixLevel(v: number): { label: string; color: string; bg: string } {
  if (v < 15) return { label: "Low", color: "#22c55e", bg: "rgba(34,197,94,0.15)" };
  if (v < 20) return { label: "Normal", color: "#3b82f6", bg: "rgba(59,130,246,0.15)" };
  if (v < 30) return { label: "High", color: "#f97316", bg: "rgba(249,115,22,0.15)" };
  return { label: "Extreme", color: "#ef4444", bg: "rgba(239,68,68,0.15)" };
}

function breadthColor(pct: number) {
  if (pct >= 60) return "var(--success)";
  if (pct >= 40) return "var(--warning)";
  return "var(--danger)";
}

function optionsSignal(vix: number) {
  if (vix >= 25) return { text: "SELL Premium (Short Straddle)", color: "var(--danger)" };
  if (vix < 15) return { text: "BUY Options (Directional)", color: "var(--success)" };
  return { text: "Neutral - Use Spreads", color: "var(--accent)" };
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function InsightsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("macro");

  // data states
  const [macro, setMacro] = useState<MacroData | null>(null);
  const [indices, setIndices] = useState<IndexData[]>([]);
  const [breadth, setBreadth] = useState<BreadthData | null>(null);
  const [vol, setVol] = useState<VolatilityData | null>(null);
  const [commodities, setCommodities] = useState<CommodityItem[]>([]);
  const [crypto, setCrypto] = useState<CryptoItem[]>([]);

  // loading flags per panel
  const [loadingMacro, setLoadingMacro] = useState(true);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [loadingVol, setLoadingVol] = useState(true);
  const [loadingComm, setLoadingComm] = useState(true);
  const [loadingCrypto, setLoadingCrypto] = useState(true);

  const fetchAll = useCallback(async () => {
    // Macro
    setLoadingMacro(true);
    fetch("/api/market/macro")
      .then((r) => r.json())
      .then((d) => setMacro(d))
      .catch(() => {})
      .finally(() => setLoadingMacro(false));

    // Health
    setLoadingHealth(true);
    Promise.all([
      fetch("/api/market/indices").then((r) => r.json()),
      fetch("/api/market/breadth").then((r) => r.json()),
    ])
      .then(([idx, br]) => {
        setIndices(idx.indices || []);
        setBreadth(br);
      })
      .catch(() => {})
      .finally(() => setLoadingHealth(false));

    // Volatility
    setLoadingVol(true);
    fetch("/api/market/volatility")
      .then((r) => r.json())
      .then((d) => setVol(d))
      .catch(() => {})
      .finally(() => setLoadingVol(false));

    // Commodities
    setLoadingComm(true);
    fetch("/api/market/commodities")
      .then((r) => r.json())
      .then((d) => setCommodities(d.commodities || []))
      .catch(() => {})
      .finally(() => setLoadingComm(false));

    // Crypto
    setLoadingCrypto(true);
    fetch("/api/market/crypto")
      .then((r) => r.json())
      .then((d) => setCrypto(d.crypto || []))
      .catch(() => {})
      .finally(() => setLoadingCrypto(false));
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 5 * 60 * 1000); // 5 min
    return () => clearInterval(interval);
  }, [fetchAll]);

  return (
    <div className="container">
      {/* Header */}
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 className="title" style={{ marginBottom: "0.25rem" }}>
          Insights
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
          Macro regime, market health, volatility, and asset signals
        </p>
      </div>

      {/* Tab Bar */}
      <div
        style={{
          display: "flex",
          gap: "0.25rem",
          marginBottom: "1.5rem",
          borderBottom: "1px solid var(--border-glass)",
          paddingBottom: "0",
        }}
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              background: activeTab === t.key ? "var(--bg-card)" : "transparent",
              color: activeTab === t.key ? "var(--text-primary)" : "var(--text-secondary)",
              border: activeTab === t.key ? "1px solid var(--border-glass)" : "1px solid transparent",
              borderBottom: activeTab === t.key ? "1px solid var(--bg-dark)" : "1px solid transparent",
              padding: "0.55rem 1.1rem",
              borderRadius: "8px 8px 0 0",
              fontSize: "0.82rem",
              fontWeight: activeTab === t.key ? 600 : 400,
              cursor: "pointer",
              transition: "all 0.15s",
              marginBottom: "-1px",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Panel Content */}
      {activeTab === "macro" && <MacroPanel data={macro} loading={loadingMacro} />}
      {activeTab === "health" && (
        <HealthPanel indices={indices} breadth={breadth} loading={loadingHealth} />
      )}
      {activeTab === "volatility" && <VolatilityPanel data={vol} loading={loadingVol} />}
      {activeTab === "commodities" && (
        <CommoditiesPanel items={commodities} loading={loadingComm} />
      )}
      {activeTab === "crypto" && <CryptoPanel items={crypto} loading={loadingCrypto} />}
    </div>
  );
}

// ── Loading Placeholder ────────────────────────────────────────────────────

function LoadingPlaceholder() {
  return (
    <div
      className="glass-panel"
      style={{
        padding: "3rem",
        textAlign: "center",
        color: "var(--text-secondary)",
        fontSize: "0.9rem",
      }}
    >
      Loading...
    </div>
  );
}

// ── Macro Panel ────────────────────────────────────────────────────────────

function MacroPanel({ data, loading }: { data: MacroData | null; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;
  if (!data) return <EmptyState label="No macro data available" />;

  const displayRegime = regimeLabel(data.regime);
  const regimeColors: Record<string, { bg: string; text: string }> = {
    "RISK ON": { bg: "rgba(34,197,94,0.18)", text: "#22c55e" },
    "RISK OFF": { bg: "rgba(239,68,68,0.18)", text: "#ef4444" },
    TRANSITION: { bg: "rgba(234,179,8,0.18)", text: "#eab308" },
  };
  const rc = regimeColors[displayRegime] || regimeColors.TRANSITION;

  return (
    <div>
      {/* Regime Badge */}
      <div
        className="glass-panel"
        style={{
          padding: "1.25rem 1.5rem",
          marginBottom: "1.25rem",
          display: "flex",
          alignItems: "center",
          gap: "1rem",
        }}
      >
        <div style={labelStyle}>Market Regime</div>
        <span
          style={{
            background: rc.bg,
            color: rc.text,
            padding: "0.35rem 1.2rem",
            borderRadius: "8px",
            fontSize: "1.1rem",
            fontWeight: 700,
            letterSpacing: "0.06em",
          }}
        >
          {displayRegime}
        </span>
      </div>

      {/* Signal Cards */}
      <div style={cardGrid3}>
        {data.signals.map((s) => {
          const dir = s.signal.toLowerCase();
          return (
            <div
              key={s.name}
              className="glass-panel"
              style={{ padding: "1rem 1.25rem" }}
            >
              <div style={labelStyle}>{s.name}</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                <span style={bigNum}>{s.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
              </div>
              <div
                style={{
                  marginTop: "0.4rem",
                  fontSize: "0.75rem",
                  color: "var(--text-secondary)",
                }}
              >
                {s.description}
              </div>
              <span
                style={{
                  ...smallBadge(
                    dir === "bullish"
                      ? "rgba(34,197,94,0.12)"
                      : dir === "bearish"
                      ? "rgba(239,68,68,0.12)"
                      : "rgba(148,163,184,0.12)",
                    signalColor(s.signal)
                  ),
                  marginTop: "0.5rem",
                }}
              >
                {s.signal}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Market Health Panel ────────────────────────────────────────────────────

function HealthPanel({
  indices,
  breadth,
  loading,
}: {
  indices: IndexData[];
  breadth: BreadthData | null;
  loading: boolean;
}) {
  if (loading) return <LoadingPlaceholder />;

  return (
    <div>
      {/* Index Cards */}
      <div style={{ ...cardGrid4, marginBottom: "1.25rem" }}>
        {indices.length === 0 && <EmptyState label="No index data" />}
        {indices.map((idx) => {
          const dma50 = idx.dma50 ?? 0;
          const dma100 = idx.dma100 ?? 0;
          const dma200 = idx.dma200 ?? 0;
          const aboveDma = (dma: number) => dma > 0 && idx.price >= dma;
          return (
            <div key={idx.symbol} className="glass-panel" style={{ padding: "1rem 1.25rem" }}>
              <div style={labelStyle}>{idx.name}</div>
              <div style={{ ...bigNum, marginBottom: "0.25rem" }}>
                {idx.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
              <span style={{ color: changeColor(idx.changePercent), fontWeight: 600, fontSize: "0.85rem" }}>
                {arrow(idx.changePercent)} {idx.changePercent > 0 ? "+" : ""}
                {idx.changePercent.toFixed(2)}%
              </span>

              {/* DMA levels */}
              {(dma50 > 0 || dma100 > 0 || dma200 > 0) && (
                <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                  {[
                    { label: "50 DMA", val: dma50 },
                    { label: "100 DMA", val: dma100 },
                    { label: "200 DMA", val: dma200 },
                  ].filter(d => d.val > 0).map((d) => (
                    <div
                      key={d.label}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: "0.72rem",
                      }}
                    >
                      <span style={{ color: "var(--text-secondary)" }}>{d.label}</span>
                      <span style={{ color: aboveDma(d.val) ? "var(--success)" : "var(--danger)", fontWeight: 600 }}>
                        {d.val.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Trend & RSI */}
              {(idx.trend || idx.rsi != null) && (
                <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  {idx.trend && (
                    <span style={smallBadge(
                      idx.trend.includes("BULL") ? "rgba(34,197,94,0.12)" : idx.trend.includes("BEAR") ? "rgba(239,68,68,0.12)" : "rgba(148,163,184,0.12)",
                      idx.trend.includes("BULL") ? "#22c55e" : idx.trend.includes("BEAR") ? "#ef4444" : "#94a3b8"
                    )}>
                      {idx.trend}
                    </span>
                  )}
                  {idx.rsi != null && (
                    <span style={{
                      fontSize: "0.7rem",
                      color: idx.rsi > 70 ? "var(--danger)" : idx.rsi < 30 ? "var(--success)" : "var(--text-secondary)",
                      fontWeight: 600,
                    }}>
                      RSI {idx.rsi.toFixed(1)}
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Breadth Meter */}
      {breadth && breadth.dma200 && (
        <div className="glass-panel" style={{ padding: "1.25rem" }}>
          <div style={labelStyle}>Market Breadth — Nifty 50</div>

          {/* 200 DMA breadth */}
          <div style={{ marginTop: "0.5rem", marginBottom: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
              <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                Above 200 DMA ({breadth.dma200.above}/{breadth.dma200.total})
              </span>
              <span style={{ fontSize: "1.1rem", fontWeight: 700, color: breadthColor(breadth.dma200.percent) }}>
                {breadth.dma200.percent.toFixed(1)}%
              </span>
            </div>
            <div style={{ height: "12px", background: "rgba(255,255,255,0.06)", borderRadius: "6px", overflow: "hidden" }}>
              <div style={{
                width: `${breadth.dma200.percent}%`,
                height: "100%",
                background: breadthColor(breadth.dma200.percent),
                borderRadius: "6px",
                transition: "width 0.4s",
              }} />
            </div>
          </div>

          {/* 50 DMA breadth */}
          {breadth.dma50 && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                <span style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                  Above 50 DMA ({breadth.dma50.above}/{breadth.dma50.total})
                </span>
                <span style={{ fontSize: "1.1rem", fontWeight: 700, color: breadthColor(breadth.dma50.percent) }}>
                  {breadth.dma50.percent.toFixed(1)}%
                </span>
              </div>
              <div style={{ height: "12px", background: "rgba(255,255,255,0.06)", borderRadius: "6px", overflow: "hidden" }}>
                <div style={{
                  width: `${breadth.dma50.percent}%`,
                  height: "100%",
                  background: breadthColor(breadth.dma50.percent),
                  borderRadius: "6px",
                  transition: "width 0.4s",
                }} />
              </div>
            </div>
          )}

          {/* Health badge */}
          <div style={{ marginTop: "0.75rem" }}>
            <span style={smallBadge(
              breadth.health === "STRONG" ? "rgba(34,197,94,0.15)" : breadth.health === "WEAK" ? "rgba(239,68,68,0.15)" : "rgba(234,179,8,0.15)",
              breadth.health === "STRONG" ? "#22c55e" : breadth.health === "WEAK" ? "#ef4444" : "#eab308"
            )}>
              {breadth.health}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Volatility Panel ───────────────────────────────────────────────────────

function VolatilityPanel({ data, loading }: { data: VolatilityData | null; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;
  if (!data) return <EmptyState label="No volatility data available" />;

  const indiaVixPrice = data.indiaVix?.price ?? 0;
  const usVixPrice = data.usVix?.price ?? 0;
  const iv = vixLevel(indiaVixPrice);
  const uv = vixLevel(usVixPrice);
  const maxVix = Math.max(indiaVixPrice, usVixPrice);
  const optSig = optionsSignal(maxVix > 0 ? maxVix : 20);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      {/* India VIX */}
      <div className="glass-panel" style={{ padding: "1.25rem" }}>
        <div style={labelStyle}>India VIX</div>
        {data.indiaVix ? (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem", marginBottom: "0.5rem" }}>
              <span style={bigNum}>{indiaVixPrice.toFixed(2)}</span>
              <span style={smallBadge(iv.bg, iv.color)}>{iv.label}</span>
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
              {data.indiaVix.description}
            </div>
          </>
        ) : (
          <div style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Data unavailable</div>
        )}
      </div>

      {/* US VIX */}
      <div className="glass-panel" style={{ padding: "1.25rem" }}>
        <div style={labelStyle}>US VIX (CBOE)</div>
        {data.usVix ? (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem", marginBottom: "0.5rem" }}>
              <span style={bigNum}>{usVixPrice.toFixed(2)}</span>
              <span style={smallBadge(uv.bg, uv.color)}>{uv.label}</span>
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
              {data.usVix.description}
            </div>
          </>
        ) : (
          <div style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>Data unavailable</div>
        )}
      </div>

      {/* Options Signal - full width */}
      <div className="glass-panel" style={{ padding: "1.25rem", gridColumn: "1 / -1" }}>
        <div style={labelStyle}>Options Signal</div>
        <div style={{ fontSize: "1.1rem", fontWeight: 600, color: optSig.color, marginTop: "0.25rem" }}>
          {optSig.text}
        </div>
      </div>
    </div>
  );
}

// ── Commodities Panel ──────────────────────────────────────────────────────

function CommoditiesPanel({ items, loading }: { items: CommodityItem[]; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;
  if (items.length === 0) return <EmptyState label="No commodities data available" />;

  return (
    <div style={cardGrid3}>
      {items.map((c) => (
        <div key={c.symbol} className="glass-panel" style={{ padding: "1.25rem" }}>
          <div style={labelStyle}>{c.name}</div>
          <div style={{ ...bigNum, marginBottom: "0.25rem" }}>
            ${c.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
          <span style={{ color: changeColor(c.changePercent), fontWeight: 600, fontSize: "0.85rem" }}>
            {arrow(c.changePercent)} {c.changePercent > 0 ? "+" : ""}
            {c.changePercent.toFixed(2)}%
          </span>
          {c.trend && (
            <div style={{ marginTop: "0.5rem" }}>
              <span style={smallBadge(
                c.trend.includes("BULL") ? "rgba(34,197,94,0.12)" : c.trend.includes("BEAR") ? "rgba(239,68,68,0.12)" : "rgba(148,163,184,0.12)",
                c.trend.includes("BULL") ? "#22c55e" : c.trend.includes("BEAR") ? "#ef4444" : "#94a3b8"
              )}>
                {c.trend}
              </span>
            </div>
          )}
          {c.rsi != null && (
            <div style={{ marginTop: "0.3rem", fontSize: "0.72rem", color: "var(--text-secondary)" }}>
              RSI: {c.rsi.toFixed(1)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── Crypto Panel ───────────────────────────────────────────────────────────

function CryptoPanel({ items, loading }: { items: CryptoItem[]; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;
  if (items.length === 0) return <EmptyState label="No crypto data available" />;

  // Determine allocation signal based on aggregate performance
  const avgChange = items.reduce((sum, c) => sum + c.changePercent, 0) / (items.length || 1);
  const allocSignal = avgChange > 2
    ? "Increase crypto allocation - momentum positive"
    : avgChange < -2
    ? "Reduce crypto exposure - momentum negative"
    : "Hold current allocation - sideways market";

  return (
    <div>
      <div style={cardGrid3}>
        {items.map((c) => (
          <div key={c.symbol} className="glass-panel" style={{ padding: "1.25rem" }}>
            <div style={labelStyle}>{c.name || c.symbol}</div>
            <div style={{ ...bigNum, marginBottom: "0.25rem" }}>
              ${c.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </div>
            <span style={{ color: changeColor(c.changePercent), fontWeight: 600, fontSize: "0.85rem" }}>
              {arrow(c.changePercent)} {c.changePercent > 0 ? "+" : ""}
              {c.changePercent.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>

      {/* Allocation Signal */}
      <div className="glass-panel" style={{ padding: "1.25rem", marginTop: "1.25rem" }}>
        <div style={labelStyle}>Allocation Signal</div>
        <div
          style={{
            fontSize: "1.05rem",
            fontWeight: 600,
            color: allocSignal.includes("Increase")
              ? "var(--success)"
              : allocSignal.includes("Reduce")
              ? "var(--danger)"
              : "var(--accent)",
            marginTop: "0.25rem",
          }}
        >
          {allocSignal}
        </div>
      </div>
    </div>
  );
}

// ── Empty State ────────────────────────────────────────────────────────────

function EmptyState({ label }: { label: string }) {
  return (
    <div
      className="glass-panel"
      style={{
        padding: "2.5rem",
        textAlign: "center",
        color: "var(--text-secondary)",
        fontSize: "0.85rem",
      }}
    >
      {label}
    </div>
  );
}
