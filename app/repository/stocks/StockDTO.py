from dataclasses import dataclass

@dataclass
class StockDTO:
    id: int = None
    created_at: str = None  # datetime 사용 가능
    updated_at: str = None  # datetime 사용 가능
    nation: str = None
    stock_code: str = None
    stock_name: str = None
    pred_price_change_3d_pct: str = None
    yesterday_close: str = None
    current_price: str = None
    today_price_change_pct: str = None
    avg5d_trading_value: str = None
    current_trading_value: str = None
    trading_value_change_pct: str = None
    image_url: str = None
    logo_image_url: str = None
    sector_code: str = None
    stock_market: str = None
    market_value: str = None
    category: str = None

