from dataclasses import dataclass
from datetime import datetime

@dataclass
class Stock:
    """Thông tin cơ bản về mã cổ phiếu"""
    symbol: str          # Mã chứng khoán (VD: HPG)
    company_name: str    # Tên công ty
    exchange: str        # Sàn giao dịch (HOSE, HNX)
    sector: str          # Nhóm ngành (Thép, Bank...)
    current_price: float # Giá tham chiếu hiện tại
    is_active: bool      # Trạng thái niêm yết

@dataclass
class MarketCandle:
    """Dữ liệu nến giá (OHLCV) để vẽ biểu đồ"""
    symbol: str
    timestamp: datetime  # Mốc thời gian nến
    open: float          # Giá mở cửa
    high: float          # Giá cao nhất
    low: float           # Giá thấp nhất
    close: float         # Giá đóng cửa
    volume: int          # Khối lượng giao dịch trong nến