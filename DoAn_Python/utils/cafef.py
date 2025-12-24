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
    url = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    params = {"Symbol": symbol, "PageIndex": 1, "PageSize": days}
    
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = r.json()
        
        if "Data" in data and "Data" in data["Data"]:
            raw_data = data["Data"]["Data"]
            result = []
            
            for row in raw_data:
                vol = 0
                # Danh sách key ưu tiên (cập nhật mới nhất)
                keys = ["nmVolume", "nmTotalVolume", "KlgiaoDichKhopLenh", "TotalVolume", "Volume", "KLKhopLenh"]
    
                for k in keys:
                    if k in row and row[k] is not None:
                        try:
                            # Xử lý cả số lẫn chuỗi "1,234.00"
                            v_str = str(row[k]).split('.')[0] # Bỏ phần thập phân nếu có
                            v_clean = v_str.replace(",", "").replace(".", "")
                            if v_clean.isdigit():
                                val = int(v_clean)
                                if val > 0:
                                    vol = val
                                    break
                        except:
                            pass
                
                # Fallback: Nếu vẫn = 0, thử tìm bất kỳ key nào có chữ "Volume" hoặc "KL"
                if vol == 0:
                    for k, v in row.items():
                        if ("Volume" in k or "KL" in k) and isinstance(v, (int, float, str)):
                            try:
                                v_clean = int(str(v).replace(",", "").replace(".", ""))
                                if v_clean > 0:
                                    vol = v_clean
                                    break
                            except:
                                pass

                result.append({
                    "date": row["Ngay"], 
                    "open": row["GiaMoCua"] * 1000,
                    "high": row["GiaCaoNhat"] * 1000,
                    "low": row["GiaThapNhat"] * 1000,
                    "close": row["GiaDongCua"] * 1000,
                    "volume": vol 
                })
            return result[::-1]
            
    except Exception as e:
        print(f"❌ Lỗi lấy lịch sử {symbol}: {e}")
    
    return []

def get_current_price(symbol):
    """
    Lấy giá hiện tại từ lịch sử (lấy cây nến mới nhất).
    """
    try:
        # Lấy 1 ngày dữ liệu mới nhất
        history = get_price_history(symbol, days=1)
        if history and len(history) > 0:
            real_price = history[-1]["close"]
            return real_price
    except Exception as e:
        print(f"❌ Lỗi lấy giá {symbol}: {e}")
        
    return 0