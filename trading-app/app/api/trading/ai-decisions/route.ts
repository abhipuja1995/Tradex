import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const dateParam = searchParams.get("date");
    const symbol = searchParams.get("symbol");
    const limit = parseInt(searchParams.get("limit") || "20");

    let query = supabase
      .from("ai_decisions")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(limit);

    if (dateParam) {
      query = query.eq("decision_date", dateParam);
    }
    if (symbol) {
      query = query.eq("symbol", symbol);
    }

    const { data, error } = await query;

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({
      decisions: data || [],
      count: data?.length || 0,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
