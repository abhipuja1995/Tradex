import { NextRequest, NextResponse } from "next/server";

const BOT_URL = process.env.TRADING_BOT_URL || "http://localhost:8100";

export async function GET() {
  try {
    const resp = await fetch(`${BOT_URL}/api/status`, {
      signal: AbortSignal.timeout(5000),
    });
    const data = await resp.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({
      state: "OFFLINE",
      paper_trading: true,
      market_open: false,
      wallet: null,
    });
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { action } = body;

    if (!["start", "pause", "stop"].includes(action)) {
      return NextResponse.json(
        { error: "action must be start, pause, or stop" },
        { status: 400 }
      );
    }

    const resp = await fetch(`${BOT_URL}/api/control/${action}`, {
      method: "POST",
      signal: AbortSignal.timeout(10000),
    });
    const data = await resp.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json(
      { error: `Bot unreachable: ${e.message}` },
      { status: 503 }
    );
  }
}
