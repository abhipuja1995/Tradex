import { NextResponse } from "next/server";

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || "8692730838:AAHrThgIgUYaG1FjBZqClLkbgSIvUxKi7O4";
const HARDCODED_CHAT_ID = process.env.TELEGRAM_CHAT_ID || "6747798646";

async function sendTelegram(chatId: string, text: string): Promise<{ ok: boolean; error?: string }> {
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
    if (data.ok) return { ok: true };
    return { ok: false, error: data.description || "Unknown Telegram error" };
  } catch (err) {
    return { ok: false, error: String(err) };
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
    if (data.ok && data.result?.id) {
      return String(data.result.id);
    }
  } catch {}

  // 3. Fallback: get chat_id from recent /start messages
  try {
    const res = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/getUpdates?limit=100&allowed_updates=["message"]`);
    const data = await res.json();
    if (data.ok && data.result?.length > 0) {
      // Find the most recent private chat (user who sent /start)
      for (let i = data.result.length - 1; i >= 0; i--) {
        const msg = data.result[i].message;
        if (msg?.chat?.type === "private" && msg?.chat?.id) {
          return String(msg.chat.id);
        }
        // Also check channel posts
        const cp = data.result[i].channel_post;
        if (cp?.chat?.id) {
          return String(cp.chat.id);
        }
      }
    }
  } catch {}

  return null;
}

function formatCurrency(val: number, currency: string = "$"): string {
  if (currency === "₹") {
    return new Intl.NumberFormat("en-IN", {
      style: "currency", currency: "INR", maximumFractionDigits: 2,
    }).format(val);
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD", maximumFractionDigits: 2,
  }).format(val);
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function buildMessage(picks: any, gold: any, macro: any, vol: any): string {
  const date = new Date().toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
  const time = new Date().toLocaleTimeString("en-IN", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
  });

  const lines: string[] = [];
  lines.push("*TradeX Pre-Market Brief*");
  lines.push(`${date} | ${time} IST`);
  lines.push("");

  // Macro regime
  const regime = macro?.regime || macro?.overallSignal || "UNKNOWN";
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
      lines.push(`${i + 1}. *${name}* (${p.setupType || "Watch"})`);
      lines.push(`   Entry: ${formatCurrency(p.entry || p.price, "₹")} | Target: ${formatCurrency(p.target, "₹")} (+${p.targetPct}%)`);
      lines.push(`   SL: ${formatCurrency(p.stopLoss, "₹")} (-${p.stopLossPct}%) | RSI: ${(p.rsi || 0).toFixed(1)} | ${p.signal || "WATCH"}`);
    });
    lines.push("");
  }

  // US picks
  if (picks?.us?.length) {
    lines.push("*US Top 5 Picks*");
    picks.us.forEach((p: any, i: number) => {
      const name = (p.name || p.symbol || "").substring(0, 20);
      lines.push(`${i + 1}. *${name}* (${p.setupType || "Watch"})`);
      lines.push(`   Entry: ${formatCurrency(p.entry || p.price)} | Target: ${formatCurrency(p.target)} (+${p.targetPct}%)`);
      lines.push(`   SL: ${formatCurrency(p.stopLoss)} (-${p.stopLossPct}%) | RSI: ${(p.rsi || 0).toFixed(1)}`);
    });
    lines.push("");
  }

  // Gold
  const g = gold || picks?.gold;
  if (g) {
    lines.push("*Gold Setup*");
    const usdPrice = g.usd?.price || g.usdPrice || 0;
    const inrPrice = g.inr?.pricePer10g || g.inrPricePer10g || 0;
    lines.push(`USD: ${formatCurrency(usdPrice)} | INR: ${formatCurrency(inrPrice, "₹")}/10g`);
    lines.push(`Signal: ${g.signal || "HOLD"} - ${g.signalReason || "Range-bound"}`);
    if (g.entry && g.targetPct) {
      lines.push(`Entry: ${formatCurrency(g.entry)} | Target: +${g.targetPct}% | SL: -${g.stopLossPct}%`);
    }
    lines.push("");
  }

  // Volatility
  if (vol) {
    const ivix = vol.indiaVix?.price ?? "N/A";
    const uvix = vol.usVix?.price ?? "N/A";
    lines.push(`*Volatility:* India VIX: ${ivix} | US VIX: ${uvix}`);
    lines.push("");
  }

  lines.push("_Generated by TradeX AI Engine_");
  return lines.join("\n");
}
/* eslint-enable @typescript-eslint/no-explicit-any */

async function fetchInternal(req: Request, path: string) {
  try {
    const url = new URL(path, req.url);
    const res = await fetch(url.toString(), { headers: { "User-Agent": "TradeX-Internal" } });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function POST(req: Request) {
  try {
    const [picks, gold, macro, vol] = await Promise.all([
      fetchInternal(req, "/api/market/picks"),
      fetchInternal(req, "/api/market/gold"),
      fetchInternal(req, "/api/market/macro"),
      fetchInternal(req, "/api/market/volatility"),
    ]);

    const message = buildMessage(picks, gold, macro, vol);

    const chatId = await findChatId();
    if (!chatId) {
      return NextResponse.json({
        success: false,
        message: "No chat found. Please send /start to @TradeX_Abhi_Puja_Bot on Telegram first, then try again.",
        howToFix: [
          "1. Open Telegram and search for @TradeX_Abhi_Puja_Bot",
          "2. Send /start to the bot",
          "3. Try sending the notification again",
          "4. Or set TELEGRAM_CHAT_ID env var on Vercel with your chat ID",
        ],
        preview: message,
      }, { status: 400 });
    }

    const result = await sendTelegram(chatId, message);
    return NextResponse.json({
      success: result.ok,
      chatId,
      message: result.ok ? "Daily brief sent to Telegram!" : `Failed: ${result.error}`,
      preview: message,
    });
  } catch (err) {
    console.error("[telegram-notify] error:", err);
    return NextResponse.json({ success: false, error: "Internal error" }, { status: 500 });
  }
}

export async function GET(req: Request) {
  try {
    // Discovery endpoint: find chat ID and return it
    const chatId = await findChatId();

    const [picks, gold, macro, vol] = await Promise.all([
      fetchInternal(req, "/api/market/picks"),
      fetchInternal(req, "/api/market/gold"),
      fetchInternal(req, "/api/market/macro"),
      fetchInternal(req, "/api/market/volatility"),
    ]);

    const message = buildMessage(picks, gold, macro, vol);
    return NextResponse.json({
      chatId: chatId || "NOT_FOUND - send /start to @TradeX_Abhi_Puja_Bot",
      preview: message,
      timestamp: new Date().toISOString(),
    });
  } catch {
    return NextResponse.json({ error: "Failed to generate preview" }, { status: 500 });
  }
}
