import requests
import random

def get_live_price(symbol):
    """
    Lấy giá chứng khoán. Ưu tiên lấy từ CafeF.
    Nếu lỗi, trả về dữ liệu giả lập (Mock) để demo không bị gián đoạn.
    """
    symbol = symbol.upper()
    
    # 1. Cố gắng lấy giá thật từ API (Fireant hoặc CafeF)
    try:
        # Dùng API search của Fireant (thường ổn định hơn CafeF cho việc lấy giá nhanh)
        url = f"https://www.fireant.vn/api/symbol/search?keywords={symbol}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=3)
        data = response.json()
        
        if len(data) > 0 and data[0]['Symbol'] == symbol:
            raw_data = data[0]
            price = float(raw_data.get('Price', 0)) * 1000 # Fireant trả về đơn vị nghìn
            change_percent = float(raw_data.get('ChangePercent', 0))
            
            # Tính giá thay đổi tuyệt đối dựa trên %
            change_value = price * (change_percent / 100)
            
            return {
                'price': price,
                'change': round(change_value, 2),
                'percent': round(change_percent, 2),
                'symbol': symbol
            }
            
    except Exception as e:
        print(f"API Error ({symbol}): {e}")

    # 2. FALLBACK: Nếu API lỗi, tự sinh dữ liệu giả lập (để Demo mượt mà)
    # Giá cơ sở giả định cho các mã phổ biến
    base_prices = {
        'HPG': 28500, 'VNM': 68000, 'FPT': 112000, 
        'STB': 20000, 'MWG': 48000, 'ACB': 25000
    }
    
    base = base_prices.get(symbol, 20000) # Mặc định 20k nếu không biết mã
    
    # Random biến động nhẹ +/- 2%
    variation = random.uniform(-0.02, 0.02) 
    fake_price = base * (1 + variation)
    fake_change = fake_price - base
    
    return {
        'price': round(fake_price, -2), # Làm tròn đến hàng trăm
        'change': round(fake_change, 2),
        'percent': round(variation * 100, 2),
        'symbol': symbol
    }