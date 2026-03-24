-- Micro-Trading System Tables
-- Run against existing Supabase PostgreSQL (alongside reviews/anomalies tables)

-- Wallet state (single row per day, upserted)
CREATE TABLE IF NOT EXISTS trading_wallet (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  total_balance numeric(12,2) NOT NULL DEFAULT 0,
  available_balance numeric(12,2) NOT NULL DEFAULT 0,
  locked_in_trades numeric(12,2) NOT NULL DEFAULT 0,
  daily_invested numeric(12,2) NOT NULL DEFAULT 0,
  daily_pnl numeric(12,2) NOT NULL DEFAULT 0,
  trade_date date NOT NULL DEFAULT CURRENT_DATE,
  updated_at timestamptz DEFAULT now()
);

-- Individual trades
CREATE TABLE IF NOT EXISTS trades (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  exchange text NOT NULL DEFAULT 'NSE',
  direction text NOT NULL CHECK (direction IN ('BUY', 'SELL')),
  quantity integer NOT NULL,
  entry_price numeric(10,2) NOT NULL,
  exit_price numeric(10,2),
  stop_loss_price numeric(10,2) NOT NULL,
  target_price numeric(10,2) NOT NULL,
  status text NOT NULL CHECK (status IN ('OPEN', 'CLOSED', 'STOPPED_OUT', 'CANCELLED')),
  pnl numeric(10,2),
  pnl_percent numeric(6,3),
  entry_time timestamptz NOT NULL DEFAULT now(),
  exit_time timestamptz,
  dhan_order_id text,
  openalgo_order_id text,
  strategy text NOT NULL DEFAULT 'HYBRID_AI_RSI',
  rsi_at_entry numeric(6,2),
  support_level numeric(10,2),
  ai_signal text,
  ai_confidence numeric(4,3),
  ai_reasoning text,
  paper_trade boolean NOT NULL DEFAULT true,
  trade_date date NOT NULL DEFAULT CURRENT_DATE,
  created_at timestamptz DEFAULT now()
);

-- Daily performance summary (one row per day)
CREATE TABLE IF NOT EXISTS daily_performance (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trade_date date UNIQUE NOT NULL,
  total_trades integer NOT NULL DEFAULT 0,
  winning_trades integer NOT NULL DEFAULT 0,
  losing_trades integer NOT NULL DEFAULT 0,
  total_invested numeric(12,2) NOT NULL DEFAULT 0,
  total_pnl numeric(12,2) NOT NULL DEFAULT 0,
  pnl_percent numeric(6,3),
  max_drawdown numeric(6,3),
  daily_cap_hit boolean NOT NULL DEFAULT false,
  loss_guard_triggered boolean NOT NULL DEFAULT false,
  profit_target_hit boolean NOT NULL DEFAULT false,
  created_at timestamptz DEFAULT now()
);

-- Trade journal (human-readable log entries)
CREATE TABLE IF NOT EXISTS trade_journal (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  trade_id uuid REFERENCES trades(id) ON DELETE SET NULL,
  trade_date date NOT NULL DEFAULT CURRENT_DATE,
  entry_type text NOT NULL CHECK (entry_type IN ('TRADE', 'OBSERVATION', 'MISTAKE', 'RULE_CHANGE')),
  title text NOT NULL,
  body text NOT NULL,
  tags text[] DEFAULT '{}',
  created_at timestamptz DEFAULT now()
);

-- Learning rules (auto-generated from mistake analysis)
CREATE TABLE IF NOT EXISTS learning_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_name text NOT NULL,
  condition_json jsonb NOT NULL,
  action text NOT NULL,
  reason text NOT NULL,
  win_rate_before numeric(6,3),
  win_rate_after numeric(6,3),
  is_active boolean NOT NULL DEFAULT false,
  created_from_trades uuid[] DEFAULT '{}',
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- AI decision logs (full TradingAgents reasoning)
CREATE TABLE IF NOT EXISTS ai_decisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  decision_date date NOT NULL DEFAULT CURRENT_DATE,
  signal text NOT NULL CHECK (signal IN ('BUY', 'SELL', 'HOLD')),
  confidence numeric(4,3),
  fundamentals_summary text,
  sentiment_summary text,
  technical_summary text,
  news_summary text,
  risk_assessment text,
  final_reasoning text,
  trade_id uuid REFERENCES trades(id) ON DELETE SET NULL,
  created_at timestamptz DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(trade_date);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_daily_perf_date ON daily_performance(trade_date);
CREATE INDEX IF NOT EXISTS idx_journal_date ON trade_journal(trade_date);
CREATE INDEX IF NOT EXISTS idx_journal_type ON trade_journal(entry_type);
CREATE INDEX IF NOT EXISTS idx_learning_active ON learning_rules(is_active);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_date ON ai_decisions(decision_date);
CREATE INDEX IF NOT EXISTS idx_ai_decisions_symbol ON ai_decisions(symbol);
