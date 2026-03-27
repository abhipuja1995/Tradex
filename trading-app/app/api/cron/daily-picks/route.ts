import { NextResponse } from "next/server";

const CRON_SECRET = process.env.CRON_SECRET || "";
const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || "8692730838:AAHrThgIgUYaG1FjBZqClLkbgSIvUxKi7O4";
const HARDCODED_CHAT_ID = process.env.TELEGRAM_CHAT_ID || "6747798646";

async function sendTelegram(chatId: string, text: string): Promise<boolean> {
  try {
    const res = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        chat_id: chatId,
        text,
        parse_mode: "Markdown",
        disable_web_page_preview: true,
      }),
    });
    const data = await res.json();
    if (!data.ok) {
      console.error("[cron] Telegram error:", data.description);
    }
    return data.ok === true;
  } catch (err) {
    console.error("[cron] sendTelegram failed:", err);
    return false;
  }
}

async function findChatId(): Promise<string | null> {
  // 1. Use env var if set
  if (HARDCODED_CHAT_ID) return HARDCODED_CHAT_ID;

  // 2. Try @TradeX_Abhi_Puja channel
  try {
    const res = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/getChat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: "@TradeX_Abhi_Puja" }),
    });
    const data = await res.json();
    if (data.ok && data.result?.id) return String(data.result.id);
  } catch {}

  // 3. Fallback: get from updates
  try {
    const res = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?limit=100`);
    const data = await res.json();
    if (data.ok && data.result?.length > 0) {
      for (let i = data.result.length - 1; i >= 0; i--) {
        const chatId =
          data.result[i].message?.chat?.id || data.result[i].channel_post?.chat?.id;
        if (chatId) return String(chatId);
      }
    }
  } catch {}

  return null;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function fmtINR(v: number): string {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(v);
}
function fmtUSD(v: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(v);
}

function buildMessage(picks: any, gold: any, macro: any, vol: any): string {
  const now = new Date();
  const date = now.toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  const time = now.toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
  });

  const lines: string[] = [];
  lines.push("*TradeX Pre-Market Brief*");
  lines.push(`${date} | ${time} IST`);
  lines.push("");

  // Macro regime
  const regime = macro?.regime || "UNKNOWN";
  lines.push(`*Market Regime:* ${String(regime).replace(/_/g, " ")}`);
  if (macro?.signals) {
    const bullish = macro.signals.filter((s: any) => s.signal === "BULLISH").length;
    const bearish = macro.signals.filter((s: any) => s.signal === "BEARISH").length;
    lines.push(`Bullish: ${bullish} | Bearish: ${bearish} | Neutral: ${macro.signals.length - bullish - bearish}`);
  }
  lines.push("");

  // India picks
  if (picks?.india?.length) {
    lines.push("*India Top 5 Picks*");
    picks.india.forEach((p: any, i: number) => {
      const name = (p.name || p.symbol || "").substring(0, 20);
      lines.push(`${i + 1}. *${name}*`);
      lines.push(`   Entry: ${fmtINR(p.price)} | Target: ${fmtINR(p.target)} (+${p.targetPct}%)`);
      lines.push(`   SL: ${fmtINR(p.stopLoss)} (-${p.stopLossPct}%) | RSI: ${(p.rsi || 0).toFixed(1)} | ${p.setupType}`);
    });
    lines.push("");
  }

  // US picks
  if (picks?.us?.length) {
    lines.push("*US Top 5 Picks*");
    picks.us.forEach((p: any, i: number) => {
      const name = (p.name || p.symbol || "").substring(0, 20);
      lines.push(`${i + 1}. *${name}*`);
      lines.push(`   Entry: ${fmtUSD(p.price)} | Target: ${fmtUSD(p.target)} (+${p.targetPct}%)`);
      lines.push(`   SL: ${fmtUSD(p.stopLoss)} (-${p.stopLossPct}%) | RSI: ${(p.rsi || 0).toFixed(1)}`);
    });
    lines.push("");
  }

  // Gold
  if (gold) {
    lines.push("*Gold*");
    lines.push(`USD: ${fmtUSD(gold.usd?.price || 0)} | INR: ${fmtINR(gold.inr?.pricePer10g || 0)}/10g`);
    lines.push(`Signal: ${gold.signal} - ${gold.signalReason}`);
    lines.push("");
  }

  // Volatility
  if (vol) {
    const iv = vol.indiaVix?.price ?? "N/A";
    const uv = vol.usVix?.price ?? "N/A";
    lines.push(`*Volatility:* India VIX: ${iv} | US VIX: ${uv}`);
    lines.push("");
  }

  lines.push("_Pre-market scan by TradeX AI Engine_");
  return lines.join("\n");
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export async function GET(req: Request) {
  // Verify cron secret (Vercel sends this header)
  const authHeader = req.headers.get("authorization");
  if (CRON_SECRET && authHeader !== `Bearer ${CRON_SECRET}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const baseUrl = new URL(req.url).origin;

    // Fetch all data in parallel
    const [picksRes, goldRes, macroRes, volRes] = await Promise.all([
      fetch(`${baseUrl}/api/market/picks`, { cache: "no-store" }).then((r) => r.json()).catch(() => null),
      fetch(`${baseUrl}/api/market/gold`, { cache: "no-store" }).then((r) => r.json()).catch(() => null),
      fetch(`${baseUrl}/api/market/macro`, { cache: "no-store" }).then((r) => r.json()).catch(() => null),
      fetch(`${baseUrl}/api/market/volatility`, { cache: "no-store" }).then((r) => r.json()).catch(() => null),
    ]);

    const message = buildMessage(picksRes, goldRes, macroRes, volRes);

    // Find chat ID and send
    const chatId = await findChatId();
    if (!chatId) {
      console.error("[cron] No Telegram chat found. Send /start to @TradeX_Abhi_Puja_Bot first, or set TELEGRAM_CHAT_ID env var.");
      return NextResponse.json({
        success: false,
        error: "No Telegram chat found. Send /start to @TradeX_Abhi_Puja_Bot or set TELEGRAM_CHAT_ID env var.",
        preview: message,
      });
    }

    const sent = await sendTelegram(chatId, message);

    console.log(`[cron] Daily picks ${sent ? "sent" : "FAILED"} to chat ${chatId}`);

    return NextResponse.json({
      success: sent,
      chatId,
      timestamp: new Date().toISOString(),
      picksCount: {
        india: picksRes?.india?.length || 0,
        us: picksRes?.us?.length || 0,
        gold: goldRes ? 1 : 0,
      },
    });
  } catch (err) {
    console.error("[cron] Daily picks error:", err);
    return NextResponse.json({ success: false, error: "Cron job failed" }, { status: 500 });
  }
}
