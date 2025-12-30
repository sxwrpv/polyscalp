from pydantic import BaseModel
import yaml

class EnvCfg(BaseModel):
    mode: str
    timezone: str = "UTC"
    log_dir: str = "./logs"

class AuthCfg(BaseModel):
    api_host: str
    ws_host: str
    api_key_env: str
    api_secret_env: str
    passphrase_env: str

class MarketsCfg(BaseModel):
    whitelist: list[str] = []
    blacklist: list[str] = []
    max_markets_active: int = 2
    min_time_to_expiry_sec: int = 120
    max_time_to_expiry_sec: int = 1200

class ScannerCfg(BaseModel):
    refresh_sec: int = 60
    min_volume_24h: float = 0
    min_depth_usd: float = 0
    max_spread_ticks: int = 3

class SignalsCfg(BaseModel):
    use_external_price: bool = True
    fair_value_model: str = "simple"
    edge_ticks: int = 1
    volatility_pause_threshold: float = 0.02

class StrategyCfg(BaseModel):
    mode: str = "scalp_maker"
    quote_refresh_ms: int = 50
    order_ttl_sec: int = 20
    order_size_shares: float = 50
    max_orders_per_market: int = 2

class RiskCfg(BaseModel):
    max_position_shares_per_market: float = 500
    max_total_position_shares: float = 1500
    max_daily_loss_usd: float = 100
    kill_on_disconnect: bool = True
    kill_on_reject_spike: bool = True
    reject_spike_count: int = 5
    reject_spike_window_sec: int = 60

class ExecutionCfg(BaseModel):
    rate_limit_per_sec: int = 8
    cancel_replace_cooldown_ms: int = 250
    slippage_guard_ticks: int = 2

class GammaCfg(BaseModel):
    base_url: str = "https://gamma-api.polymarket.com"
    slug_prefix: str = "btc-updown-15m-"
    interval_sec: int = 900
    lookahead_intervals: int = 12

class BotConfig(BaseModel):
    gamma: GammaCfg
    env: EnvCfg
    auth: AuthCfg
    markets: MarketsCfg
    scanner: ScannerCfg
    signals: SignalsCfg
    strategy: StrategyCfg
    risk: RiskCfg
    execution: ExecutionCfg

def load_config(path: str) -> BotConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return BotConfig(**data)