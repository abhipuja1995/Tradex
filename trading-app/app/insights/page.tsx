"use client";

import React, { useEffect, useState, useCallback, Component, ReactNode } from "react";

// ── Error Boundary ──────────────────────────────────────────────────────────

class PanelErrorBoundary extends Component<
  { children: ReactNode; fallback?: string },
  { hasError: boolean; error: string }
> {
  constructor(props: { children: ReactNode; fallback?: string }) {
    super(props);
    this.state = { hasError: false, error: "" };
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div
          className="glass-panel"
          style={{ padding: "2rem", textAlign: "center", color: "#f97316", fontSize: "0.85rem" }}
        >
          {this.props.fallback || "Failed to render panel"}: {this.state.error}
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Safe helpers ────────────────────────────────────────────────────────────

function safeNum(v: unknown, fallback = 0): number {
  if (v == null) return fallback;
  const n = Number(v);
  return isNaN(n) ? fallback : n;
}

function safeStr(v: unknown, fallback = ""): string {
  if (v == null) return fallback;
  return String(v);
}

function safeFixed(v: unknown, digits = 2): string {
  return safeNum(v).toFixed(digits);
}

function safePct(v: unknown): string {
  const n = safeNum(v);
  return (n > 0 ? "+" : "") + n.toFixed(2) + "%";
}

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

// ── Color Helpers ──────────────────────────────────────────────────────────

function changeColor(v: number) {
  return v > 0 ? "#22c55e" : v < 0 ? "#ef4444" : "#94a3b8";
}

function arrow(v: number) {
  return v > 0 ? "\u2191" : v < 0 ? "\u2193" : "\u2013";
}

function signalColor(d: string) {
  const lower = safeStr(d).toLowerCase();
  if (lower === "bullish") return "#22c55e";
  if (lower === "bearish") return "#ef4444";
  return "#94a3b8";
}

function signalBg(d: string) {
  const lower = safeStr(d).toLowerCase();
  if (lower === "bullish") return "rgba(34,197,94,0.12)";
  if (lower === "bearish") return "rgba(239,68,68,0.12)";
  return "rgba(148,163,184,0.12)";
}

function regimeLabel(regime: string): string {
  return safeStr(regime).replace(/_/g, " ");
}

function vixLevel(v: number): { label: string; color: string; bg: string } {
  if (v < 15) return { label: "Low", color: "#22c55e", bg: "rgba(34,197,94,0.15)" };
  if (v < 20) return { label: "Normal", color: "#3b82f6", bg: "rgba(59,130,246,0.15)" };
  if (v < 30) return { label: "High", color: "#f97316", bg: "rgba(249,115,22,0.15)" };
  return { label: "Extreme", color: "#ef4444", bg: "rgba(239,68,68,0.15)" };
}

function breadthColor(pct: number) {
  if (pct >= 60) return "#22c55e";
  if (pct >= 40) return "#eab308";
  return "#ef4444";
}

function trendBadgeColor(trend: string) {
  if (trend.includes("BULL")) return { bg: "rgba(34,197,94,0.12)", color: "#22c55e" };
  if (trend.includes("BEAR")) return { bg: "rgba(239,68,68,0.12)", color: "#ef4444" };
  return { bg: "rgba(148,163,184,0.12)", color: "#94a3b8" };
}

function optionsSignal(vix: number) {
  if (vix >= 25) return { text: "SELL Premium (Short Straddle)", color: "#ef4444" };
  if (vix < 15) return { text: "BUY Options (Directional)", color: "#22c55e" };
  return { text: "Neutral - Use Spreads", color: "#3b82f6" };
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function InsightsPage() {
  const [activeTab, setActiveTab] = useState<TabKey>("macro");

  /* eslint-disable @typescript-eslint/no-explicit-any */
  const [macro, setMacro] = useState<any>(null);
  const [indices, setIndices] = useState<any[]>([]);
  const [breadth, setBreadth] = useState<any>(null);
  const [vol, setVol] = useState<any>(null);
  const [commodities, setCommodities] = useState<any[]>([]);
  const [crypto, setCrypto] = useState<any[]>([]);
  /* eslint-enable @typescript-eslint/no-explicit-any */

  const [loadingMacro, setLoadingMacro] = useState(true);
  const [loadingHealth, setLoadingHealth] = useState(true);
  const [loadingVol, setLoadingVol] = useState(true);
  const [loadingComm, setLoadingComm] = useState(true);
  const [loadingCrypto, setLoadingCrypto] = useState(true);

  const fetchAll = useCallback(async () => {
    setLoadingMacro(true);
    fetch("/api/market/macro")
      .then((r) => r.json())
      .then((d) => { try { setMacro(d); } catch {} })
      .catch(() => {})
      .finally(() => setLoadingMacro(false));

    setLoadingHealth(true);
    Promise.all([
      fetch("/api/market/indices").then((r) => r.json()).catch(() => ({ indices: [] })),
      fetch("/api/market/breadth").then((r) => r.json()).catch(() => null),
    ])
      .then(([idx, br]) => {
        try {
          setIndices(Array.isArray(idx?.indices) ? idx.indices : []);
          setBreadth(br);
        } catch {}
      })
      .catch(() => {})
      .finally(() => setLoadingHealth(false));

    setLoadingVol(true);
    fetch("/api/market/volatility")
      .then((r) => r.json())
      .then((d) => { try { setVol(d); } catch {} })
      .catch(() => {})
      .finally(() => setLoadingVol(false));

    setLoadingComm(true);
    fetch("/api/market/commodities")
      .then((r) => r.json())
      .then((d) => { try { setCommodities(Array.isArray(d?.commodities) ? d.commodities : []); } catch {} })
      .catch(() => {})
      .finally(() => setLoadingComm(false));

    setLoadingCrypto(true);
    fetch("/api/market/crypto")
      .then((r) => r.json())
      .then((d) => { try { setCrypto(Array.isArray(d?.crypto) ? d.crypto : []); } catch {} })
      .catch(() => {})
      .finally(() => setLoadingCrypto(false));
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  return (
    <div className="container">
      <div style={{ marginBottom: "1.25rem" }}>
        <h1 className="title" style={{ marginBottom: "0.25rem" }}>Insights</h1>
        <p style={{ color: "#94a3b8", fontSize: "0.85rem" }}>
          Macro regime, market health, volatility, and asset signals
        </p>
      </div>

      {/* Tab Bar */}
      <div
        style={{
          display: "flex",
          gap: "0.25rem",
          marginBottom: "1.5rem",
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          paddingBottom: "0",
        }}
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              background: activeTab === t.key ? "rgba(255,255,255,0.05)" : "transparent",
              color: activeTab === t.key ? "#f1f5f9" : "#94a3b8",
              border: activeTab === t.key ? "1px solid rgba(255,255,255,0.1)" : "1px solid transparent",
              borderBottom: activeTab === t.key ? "1px solid #0f172a" : "1px solid transparent",
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

      <PanelErrorBoundary fallback="Macro panel error">
        {activeTab === "macro" && <MacroPanel data={macro} loading={loadingMacro} />}
      </PanelErrorBoundary>
      <PanelErrorBoundary fallback="Market Health panel error">
        {activeTab === "health" && <HealthPanel indices={indices} breadth={breadth} loading={loadingHealth} />}
      </PanelErrorBoundary>
      <PanelErrorBoundary fallback="Volatility panel error">
        {activeTab === "volatility" && <VolatilityPanel data={vol} loading={loadingVol} />}
      </PanelErrorBoundary>
      <PanelErrorBoundary fallback="Commodities panel error">
        {activeTab === "commodities" && <CommoditiesPanel items={commodities} loading={loadingComm} />}
      </PanelErrorBoundary>
      <PanelErrorBoundary fallback="Crypto panel error">
        {activeTab === "crypto" && <CryptoPanel items={crypto} loading={loadingCrypto} />}
      </PanelErrorBoundary>
    </div>
  );
}

// ── Loading / Empty ────────────────────────────────────────────────────────

function LoadingPlaceholder() {
  return (
    <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", color: "#94a3b8", fontSize: "0.9rem" }}>
      Loading...
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="glass-panel" style={{ padding: "2.5rem", textAlign: "center", color: "#94a3b8", fontSize: "0.85rem" }}>
      {label}
    </div>
  );
}

// ── Macro Panel ────────────────────────────────────────────────────────────

/* eslint-disable @typescript-eslint/no-explicit-any */
function MacroPanel({ data, loading }: { data: any; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;
  if (!data) return <EmptyState label="No macro data available" />;

  const regime = safeStr(data.regime, "TRANSITION");
  const displayRegime = regimeLabel(regime);
  const signals: any[] = Array.isArray(data.signals) ? data.signals : [];

  const regimeColors: Record<string, { bg: string; text: string }> = {
    "RISK ON": { bg: "rgba(34,197,94,0.18)", text: "#22c55e" },
    "RISK OFF": { bg: "rgba(239,68,68,0.18)", text: "#ef4444" },
    TRANSITION: { bg: "rgba(234,179,8,0.18)", text: "#eab308" },
  };
  const rc = regimeColors[displayRegime] || regimeColors.TRANSITION;

  return (
    <div>
      <div className="glass-panel" style={{ padding: "1.25rem 1.5rem", marginBottom: "1.25rem", display: "flex", alignItems: "center", gap: "1rem" }}>
        <div style={labelStyle}>Market Regime</div>
        <span style={{ background: rc.bg, color: rc.text, padding: "0.35rem 1.2rem", borderRadius: "8px", fontSize: "1.1rem", fontWeight: 700, letterSpacing: "0.06em" }}>
          {displayRegime}
        </span>
      </div>

      <div style={cardGrid3}>
        {signals.map((s: any, i: number) => {
          const sig = safeStr(s?.signal, "NEUTRAL");
          const name = safeStr(s?.name, `Signal ${i + 1}`);
          const value = safeNum(s?.value);
          const desc = safeStr(s?.description);

          return (
            <div key={name + i} className="glass-panel" style={{ padding: "1rem 1.25rem" }}>
              <div style={labelStyle}>{name}</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem" }}>
                <span style={bigNum}>{value.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
              </div>
              {desc && (
                <div style={{ marginTop: "0.4rem", fontSize: "0.75rem", color: "#94a3b8" }}>
                  {desc}
                </div>
              )}
              <span style={{ ...smallBadge(signalBg(sig), signalColor(sig)), marginTop: "0.5rem" }}>
                {sig}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Market Health Panel ────────────────────────────────────────────────────

function HealthPanel({ indices, breadth, loading }: { indices: any[]; breadth: any; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;

  const idxList: any[] = Array.isArray(indices) ? indices : [];

  return (
    <div>
      <div style={{ ...cardGrid4, marginBottom: "1.25rem" }}>
        {idxList.length === 0 && <EmptyState label="No index data" />}
        {idxList.map((idx: any, i: number) => {
          const name = safeStr(idx?.name, safeStr(idx?.symbol, `Index ${i}`));
          const sym = safeStr(idx?.symbol, `idx-${i}`);
          const price = safeNum(idx?.price);
          const changePct = safeNum(idx?.changePercent);
          const dma50 = safeNum(idx?.dma50);
          const dma100 = safeNum(idx?.dma100);
          const dma200 = safeNum(idx?.dma200);
          const trend = safeStr(idx?.trend);
          const rsi = idx?.rsi != null ? safeNum(idx.rsi) : null;

          return (
            <div key={sym + i} className="glass-panel" style={{ padding: "1rem 1.25rem" }}>
              <div style={labelStyle}>{name}</div>
              <div style={{ ...bigNum, marginBottom: "0.25rem" }}>
                {price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
              <span style={{ color: changeColor(changePct), fontWeight: 600, fontSize: "0.85rem" }}>
                {arrow(changePct)} {safePct(changePct)}
              </span>

              {(dma50 > 0 || dma100 > 0 || dma200 > 0) && (
                <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                  {[
                    { label: "50 DMA", val: dma50 },
                    { label: "100 DMA", val: dma100 },
                    { label: "200 DMA", val: dma200 },
                  ].filter(d => d.val > 0).map((d) => (
                    <div key={d.label} style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem" }}>
                      <span style={{ color: "#94a3b8" }}>{d.label}</span>
                      <span style={{ color: price >= d.val ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
                        {d.val.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {(trend || rsi != null) && (
                <div style={{ marginTop: "0.5rem", display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                  {trend && (() => { const tc = trendBadgeColor(trend); return <span style={smallBadge(tc.bg, tc.color)}>{trend}</span>; })()}
                  {rsi != null && (
                    <span style={{ fontSize: "0.7rem", color: rsi > 70 ? "#ef4444" : rsi < 30 ? "#22c55e" : "#94a3b8", fontWeight: 600 }}>
                      RSI {safeFixed(rsi, 1)}
                    </span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {breadth && breadth.dma200 && (
        <div className="glass-panel" style={{ padding: "1.25rem" }}>
          <div style={labelStyle}>Market Breadth — Nifty 50</div>

          <div style={{ marginTop: "0.5rem", marginBottom: "1rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
              <span style={{ fontSize: "0.78rem", color: "#94a3b8" }}>
                Above 200 DMA ({safeNum(breadth.dma200?.above)}/{safeNum(breadth.dma200?.total)})
              </span>
              <span style={{ fontSize: "1.1rem", fontWeight: 700, color: breadthColor(safeNum(breadth.dma200?.percent)) }}>
                {safeFixed(breadth.dma200?.percent, 1)}%
              </span>
            </div>
            <div style={{ height: "12px", background: "rgba(255,255,255,0.06)", borderRadius: "6px", overflow: "hidden" }}>
              <div style={{ width: `${safeNum(breadth.dma200?.percent)}%`, height: "100%", background: breadthColor(safeNum(breadth.dma200?.percent)), borderRadius: "6px", transition: "width 0.4s" }} />
            </div>
          </div>

          {breadth.dma50 && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.3rem" }}>
                <span style={{ fontSize: "0.78rem", color: "#94a3b8" }}>
                  Above 50 DMA ({safeNum(breadth.dma50?.above)}/{safeNum(breadth.dma50?.total)})
                </span>
                <span style={{ fontSize: "1.1rem", fontWeight: 700, color: breadthColor(safeNum(breadth.dma50?.percent)) }}>
                  {safeFixed(breadth.dma50?.percent, 1)}%
                </span>
              </div>
              <div style={{ height: "12px", background: "rgba(255,255,255,0.06)", borderRadius: "6px", overflow: "hidden" }}>
                <div style={{ width: `${safeNum(breadth.dma50?.percent)}%`, height: "100%", background: breadthColor(safeNum(breadth.dma50?.percent)), borderRadius: "6px", transition: "width 0.4s" }} />
              </div>
            </div>
          )}

          {breadth.health && (
            <div style={{ marginTop: "0.75rem" }}>
              <span style={smallBadge(
                breadth.health === "STRONG" ? "rgba(34,197,94,0.15)" : breadth.health === "WEAK" ? "rgba(239,68,68,0.15)" : "rgba(234,179,8,0.15)",
                breadth.health === "STRONG" ? "#22c55e" : breadth.health === "WEAK" ? "#ef4444" : "#eab308"
              )}>
                {safeStr(breadth.health)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Volatility Panel ───────────────────────────────────────────────────────

function VolatilityPanel({ data, loading }: { data: any; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;
  if (!data) return <EmptyState label="No volatility data available" />;

  const indiaVixPrice = safeNum(data.indiaVix?.price);
  const usVixPrice = safeNum(data.usVix?.price);
  const iv = vixLevel(indiaVixPrice);
  const uv = vixLevel(usVixPrice);
  const maxVix = Math.max(indiaVixPrice, usVixPrice);
  const optSig = optionsSignal(maxVix > 0 ? maxVix : 20);

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      <div className="glass-panel" style={{ padding: "1.25rem" }}>
        <div style={labelStyle}>India VIX</div>
        {data.indiaVix ? (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem", marginBottom: "0.5rem" }}>
              <span style={bigNum}>{safeFixed(indiaVixPrice)}</span>
              <span style={smallBadge(iv.bg, iv.color)}>{iv.label}</span>
            </div>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>{safeStr(data.indiaVix?.description)}</div>
          </>
        ) : (
          <div style={{ color: "#94a3b8", fontSize: "0.85rem" }}>Data unavailable</div>
        )}
      </div>

      <div className="glass-panel" style={{ padding: "1.25rem" }}>
        <div style={labelStyle}>US VIX (CBOE)</div>
        {data.usVix ? (
          <>
            <div style={{ display: "flex", alignItems: "baseline", gap: "0.75rem", marginBottom: "0.5rem" }}>
              <span style={bigNum}>{safeFixed(usVixPrice)}</span>
              <span style={smallBadge(uv.bg, uv.color)}>{uv.label}</span>
            </div>
            <div style={{ fontSize: "0.75rem", color: "#94a3b8" }}>{safeStr(data.usVix?.description)}</div>
          </>
        ) : (
          <div style={{ color: "#94a3b8", fontSize: "0.85rem" }}>Data unavailable</div>
        )}
      </div>

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

function CommoditiesPanel({ items, loading }: { items: any[]; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;
  const list: any[] = Array.isArray(items) ? items : [];
  if (list.length === 0) return <EmptyState label="No commodities data available" />;

  return (
    <div style={cardGrid3}>
      {list.map((c: any, i: number) => {
        const name = safeStr(c?.name, safeStr(c?.symbol, `Commodity ${i}`));
        const sym = safeStr(c?.symbol, `comm-${i}`);
        const price = safeNum(c?.price);
        const changePct = safeNum(c?.changePercent);
        const trend = safeStr(c?.trend);
        const rsi = c?.rsi != null ? safeNum(c.rsi) : null;

        return (
          <div key={sym + i} className="glass-panel" style={{ padding: "1.25rem" }}>
            <div style={labelStyle}>{name}</div>
            <div style={{ ...bigNum, marginBottom: "0.25rem" }}>
              ${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
            </div>
            <span style={{ color: changeColor(changePct), fontWeight: 600, fontSize: "0.85rem" }}>
              {arrow(changePct)} {safePct(changePct)}
            </span>
            {trend && (
              <div style={{ marginTop: "0.5rem" }}>
                {(() => { const tc = trendBadgeColor(trend); return <span style={smallBadge(tc.bg, tc.color)}>{trend}</span>; })()}
              </div>
            )}
            {rsi != null && (
              <div style={{ marginTop: "0.3rem", fontSize: "0.72rem", color: "#94a3b8" }}>
                RSI: {safeFixed(rsi, 1)}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Crypto Panel ───────────────────────────────────────────────────────────

function CryptoPanel({ items, loading }: { items: any[]; loading: boolean }) {
  if (loading) return <LoadingPlaceholder />;
  const list: any[] = Array.isArray(items) ? items : [];
  if (list.length === 0) return <EmptyState label="No crypto data available" />;

  const avgChange = list.reduce((sum, c) => sum + safeNum(c?.changePercent), 0) / (list.length || 1);
  const allocSignal = avgChange > 2
    ? "Increase crypto allocation - momentum positive"
    : avgChange < -2
    ? "Reduce crypto exposure - momentum negative"
    : "Hold current allocation - sideways market";

  return (
    <div>
      <div style={cardGrid3}>
        {list.map((c: any, i: number) => {
          const name = safeStr(c?.name, safeStr(c?.symbol, `Crypto ${i}`));
          const sym = safeStr(c?.symbol, `crypto-${i}`);
          const price = safeNum(c?.price);
          const changePct = safeNum(c?.changePercent);

          return (
            <div key={sym + i} className="glass-panel" style={{ padding: "1.25rem" }}>
              <div style={labelStyle}>{name}</div>
              <div style={{ ...bigNum, marginBottom: "0.25rem" }}>
                ${price.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
              <span style={{ color: changeColor(changePct), fontWeight: 600, fontSize: "0.85rem" }}>
                {arrow(changePct)} {safePct(changePct)}
              </span>
            </div>
          );
        })}
      </div>

      <div className="glass-panel" style={{ padding: "1.25rem", marginTop: "1.25rem" }}>
        <div style={labelStyle}>Allocation Signal</div>
        <div
          style={{
            fontSize: "1.05rem",
            fontWeight: 600,
            color: allocSignal.includes("Increase") ? "#22c55e" : allocSignal.includes("Reduce") ? "#ef4444" : "#3b82f6",
            marginTop: "0.25rem",
          }}
        >
          {allocSignal}
        </div>
      </div>
    </div>
  );
}
/* eslint-enable @typescript-eslint/no-explicit-any */
