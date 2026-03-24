import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const dateParam = searchParams.get("date");
    const entryType = searchParams.get("type");
    const limit = parseInt(searchParams.get("limit") || "50");

    let query = supabase
      .from("trade_journal")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(limit);

    if (dateParam) {
      query = query.eq("trade_date", dateParam);
    }
    if (entryType) {
      query = query.eq("entry_type", entryType);
    }

    const { data, error } = await query;

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }

    return NextResponse.json({ entries: data || [], count: data?.length || 0 });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 500 });
  }
}
