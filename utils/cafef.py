import requests
import time
from datetime import datetime

# Header giả lập Chrome để CafeF không chặn
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://s.cafef.vn/"
}

def get_price_history(symbol, days=365):
    """
    Lấy dữ liệu thật từ CafeF.
    """
    url = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    params = {
        "Symbol": symbol,
        "PageIndex": 1,
        "PageSize": days
    }
    
    try:
        # Gọi API CafeF
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = r.json()
        
        # In ra để kiểm tra xem CafeF trả về gì (Debug)
        # print(f"API Debug {symbol}: {str(data)[:100]}...") 

        if "Data" in data and "Data" in data["Data"]:
            raw_data = data["Data"]["Data"]
            result = []
            for row in raw_data:
                # Xử lý vấn đề CafeF đổi tên key liên tục
                vol = 0
                if "KLKhopLenh" in row: vol = row["KLKhopLenh"]
                elif "Volume" in row: vol = row["Volume"]
                elif "khoi_luong" in row: vol = row["khoi_luong"]
                
                result.append({
                    "date": row["Ngay"], # dd/mm/yyyy
                    "open": row["GiaMoCua"] * 1000,
                    "high": row["GiaCaoNhat"] * 1000,
                    "low": row["GiaThapNhat"] * 1000,
                    "close": row["GiaDongCua"] * 1000,
                    "volume": vol
                })
            return result[::-1] # Đảo ngược: Cũ -> Mới
            
    except Exception as e:
        print(f"❌ Lỗi lấy lịch sử {symbol}: {e}")
    
    return []

def get_current_price(symbol):
    """
    Lấy giá hiện tại từ lịch sử (lấy cây nến mới nhất).
    Tuyệt đối KHÔNG random.
    """
    try:
        # Lấy 1 ngày dữ liệu mới nhất
        history = get_price_history(symbol, days=1)
        if history and len(history) > 0:
            real_price = history[-1]["close"]
            print(f"✅ {symbol}: {real_price:,.0f} VNĐ") # In ra terminal để xác nhận
            return real_price
    except Exception as e:
        print(f"❌ Lỗi lấy giá {symbol}: {e}")
        
    return 0