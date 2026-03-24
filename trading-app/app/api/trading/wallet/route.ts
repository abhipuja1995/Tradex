import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET() {
  try {
    const today = new Date().toISOString().split("T")[0];

    const { data, error } = await supabase
      .from("trading_wallet")
      .select("*")
      .eq("trade_date", today)
      .single();

    if (error && error.code !== "PGRST116") {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({
      wallet: data || {
        total_balance: 0,
        available_balance: 0,
        locked_in_trades: 0,
        daily_invested: 0,
        daily_pnl: 0,
        trade_date: today,
      },
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
