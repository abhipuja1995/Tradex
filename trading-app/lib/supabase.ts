import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || "";

export const supabase = createClient(supabaseUrl, supabaseKey);

// Trading Types
export type Trade = {
  id: string;
  symbol: string;
  exchange: string;
  direction: "BUY" | "SELL";
  quantity: number;
  entry_price: number;
  exit_price: number | null;
  stop_loss_price: number;
  target_price: number;
  status: "OPEN" | "CLOSED" | "STOPPED_OUT" | "CANCELLED";
  pnl: number | null;
  pnl_percent: number | null;
  entry_time: string;
  exit_time: string | null;
  dhan_order_id: string | null;
  openalgo_order_id: string | null;
  strategy: string;
  rsi_at_entry: number | null;
  support_level: number | null;
  ai_signal: string | null;
  ai_confidence: number | null;
  ai_reasoning: string | null;
  paper_trade: boolean;
  trade_date: string;
  created_at: string;
};

export type TradingWallet = {
  id: string;
  total_balance: number;
  available_balance: number;
  locked_in_trades: number;
  daily_invested: number;
  daily_pnl: number;
  trade_date: string;
  updated_at: string;
};

export type DailyPerformance = {
  id: string;
  trade_date: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  total_invested: number;
  total_pnl: number;
  pnl_percent: number | null;
  max_drawdown: number | null;
  daily_cap_hit: boolean;
  loss_guard_triggered: boolean;
  profit_target_hit: boolean;
  created_at: string;
};

export type JournalEntry = {
  id: string;
  trade_id: string | null;
  trade_date: string;
  entry_type: "TRADE" | "OBSERVATION" | "MISTAKE" | "RULE_CHANGE";
  title: string;
  body: string;
  tags: string[];
  created_at: string;
};

export type LearningRule = {
  id: string;
  rule_name: string;
  condition_json: Record<string, any>;
  action: string;
  reason: string;
  win_rate_before: number | null;
  win_rate_after: number | null;
  is_active: boolean;
  created_from_trades: string[];
  created_at: string;
  updated_at: string;
};

export type AIDecision = {
  id: string;
  symbol: string;
  decision_date: string;
  signal: "BUY" | "SELL" | "HOLD";
  confidence: number | null;
  fundamentals_summary: string | null;
  sentiment_summary: string | null;
  technical_summary: string | null;
  news_summary: string | null;
  risk_assessment: string | null;
  final_reasoning: string | null;
  trade_id: string | null;
  created_at: string;
};
