import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "TradeX — Micro-Trading Dashboard",
  description: "Automated micro-trading system with AI-powered signals",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <nav
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0.75rem 2rem",
            borderBottom: "1px solid rgba(255,255,255,0.05)",
          }}
        >
          <a
            href="/"
            style={{
              textDecoration: "none",
              fontSize: "1rem",
              fontWeight: 700,
              background: "linear-gradient(135deg, #60a5fa, #34d399)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              letterSpacing: "-0.02em",
            }}
          >
            TradeX
          </a>
          <div style={{ display: "flex", gap: "1.5rem" }}>
            <a
              href="/"
              style={{
                color: "#94a3b8",
                textDecoration: "none",
                fontSize: "0.85rem",
              }}
            >
              Dashboard
            </a>
            <a
              href="/trading/journal"
              style={{
                color: "#94a3b8",
                textDecoration: "none",
                fontSize: "0.85rem",
              }}
            >
              Journal
            </a>
            <a
              href="/trading/settings"
              style={{
                color: "#94a3b8",
                textDecoration: "none",
                fontSize: "0.85rem",
              }}
            >
              Settings
            </a>
          </div>
        </nav>
        {children}
      </body>
    </html>
  );
}
