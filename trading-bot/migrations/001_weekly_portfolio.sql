-- Weekly Portfolio table for tracking paper investments in weekly recommendation picks
CREATE TABLE IF NOT EXISTS weekly_portfolio (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    week_start_date DATE NOT NULL,
    symbol TEXT NOT NULL,
    entry_price NUMERIC(12, 2) NOT NULL,
    entry_date DATE NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    invested_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    current_price NUMERIC(12, 2),
    pnl NUMERIC(14, 2) DEFAULT 0,
    pnl_percent NUMERIC(8, 2) DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    source TEXT DEFAULT 'weekly',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_weekly_portfolio_status ON weekly_portfolio(status);
CREATE INDEX IF NOT EXISTS idx_weekly_portfolio_week ON weekly_portfolio(week_start_date);
CREATE INDEX IF NOT EXISTS idx_weekly_portfolio_symbol ON weekly_portfolio(symbol);
