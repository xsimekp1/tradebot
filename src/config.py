from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL_ASYNC: str = "postgresql+asyncpg://localhost/tradebot"

    # Broker selection: "alpaca" or "oanda"
    BROKER: str = "alpaca"

    # Alpaca settings
    ALPACA_API_KEY: str = ""
    ALPACA_SECRET_KEY: str = ""
    ALPACA_BASE_URL: str = "https://paper-api.alpaca.markets"
    ALPACA_PAPER: bool = True

    # OANDA settings (for forex trading)
    OANDA_API_KEY: str = ""
    OANDA_ACCOUNT_ID: str = ""
    OANDA_PRACTICE: bool = True  # True for demo, False for live

    # "stock", "crypto", or "forex"
    ASSET_CLASS: str = "stock"
    SYMBOL: str = "SPY"
    LOOP_INTERVAL_SECONDS: int = 60
    SCORE_LONG_THRESHOLD: float = 0.15
    SCORE_SHORT_THRESHOLD: float = -0.15
    POSITION_SIZE_USD: float = 1000.0
    # How many bars to fetch for signal computation
    BARS_LIMIT: int = 600
    # Nightly mutation: number of days of trades to evaluate
    MUTATION_LOOKBACK_DAYS: int = 7


settings = Settings()
