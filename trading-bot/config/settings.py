"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Dhan Broker
    dhan_client_id: str = ""
    dhan_access_token: str = ""

    # OpenAlgo
    openalgo_url: str = "http://localhost:5000"
    openalgo_api_key: str = ""

    # Supabase
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # LLM Provider
    llm_provider: str = "openai"
    xai_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Trading Parameters
    paper_trading: bool = True
    daily_cap_inr: float = 840.0
    per_trade_cap_inr: float = 168.0
    max_trades_per_day: int = 5
    stop_loss_percent: float = 1.0
    daily_max_loss_percent: float = 3.0
    target_profit_percent: float = 1.5
    daily_target_percent: float = 5.0
    rsi_oversold: int = 30
    rsi_period: int = 14
    scan_interval_seconds: int = 60
    consecutive_loss_limit: int = 3

    # Market Hours (IST, 24h format)
    market_open: str = "09:15"
    market_close: str = "15:30"
    scan_stop: str = "15:15"
    force_close: str = "15:25"

    # FastAPI
    fastapi_host: str = "0.0.0.0"
    fastapi_port: int = 8100
    port: int = 0  # Railway sets PORT env var; if set, overrides fastapi_port

    @property
    def effective_port(self) -> int:
        """Railway sets PORT env var. Use it if available, else fastapi_port."""
        return self.port if self.port > 0 else self.fastapi_port


settings = Settings()
