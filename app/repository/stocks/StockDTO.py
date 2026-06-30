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
    graph_file: str = None
    logo_image_url: str = None
    sector_code: str = None
    stock_market: str = None
    market_value: str = None
    category: str = None
    target: str = None
    find_rule: str = None
    last_close: str = None
    user_id: int = None
    flag: bool = None

    @classmethod
    def from_json(cls, data: dict) -> "StockDTO":
        last_close = data.get("last_close") or None
        return cls(
            nation=data.get("nation") or None,
            stock_code=data.get("stock_code") or None,
            stock_name=data.get("stock_name") or None,
            pred_price_change_3d_pct=data.get("pred_price_change_3d_pct") or None,
            yesterday_close=data.get("yesterday_close") or None,
            current_price=str(int(float(last_close))) if last_close else (data.get("current_price") or None),
            today_price_change_pct=data.get("today_price_change_pct") or None,
            avg5d_trading_value=data.get("avg5d_trading_value") or None,
            current_trading_value=data.get("current_trading_value") or None,
            trading_value_change_pct=data.get("trading_value_change_pct") or None,
            graph_file=data.get("graph_file") or None,
            logo_image_url=data.get("logo_image_url") or None,
            sector_code=data.get("sector_code") or None,
            stock_market=data.get("stock_market") or None,
            market_value=data.get("market_value") or None,
            category=data.get("category") or None,
            target=data.get("target") or None,
            find_rule=data.get("find_rule") or None,
            last_close=last_close,
            created_at=data.get("created_at") or None,
        )

