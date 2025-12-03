import requests
import pandas as pd
import os

def fetch_and_save_csv(symbol):
    # 1. Cấu hình request
    url = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    params = {
        "Symbol": symbol,
        "StartDate": "01/01/2000", # Lấy từ năm 2000 cho đủ
        "EndDate": pd.Timestamp.now().strftime("%d/%m/%Y"),
        "PageIndex": 1,
        "PageSize": 10000,
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    try:
        # 2. Gọi API
        print(f"Đang tải dữ liệu {symbol}...")
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        
        # 3. Parse JSON (Xử lý cấu trúc lằng nhằng của CafeF)
        data = resp.json()
        records = []
        
        if isinstance(data, dict) and "Data" in data and "Data" in data["Data"]:
            records = data["Data"]["Data"]
        else:
            print(f"Cấu trúc JSON lạ hoặc không có dữ liệu cho {symbol}")
            return

        # 4. Tạo DataFrame và Lưu CSV
        if records:
            df = pd.DataFrame(records)
            
            # Mapping tên cột cho chuẩn quốc tế (như code cũ của bạn)
            rename_map = {
                "Ngay": "Date",
                "GiaMoCua": "Open",
                "GiaCaoNhat": "High",
                "GiaThapNhat": "Low",
                "GiaDongCua": "Close",
                "KhoiLuongKhopLenh": "Volume",
                "GiaDieuChinh": "AdjClose"
            }
            df.rename(columns=rename_map, inplace=True)
            
            # Chỉ giữ lại các cột cần thiết
            cols_to_keep = ["Date", "Open", "High", "Low", "Close", "AdjClose", "Volume"]
            # Lọc chỉ lấy những cột có trong data trả về
            final_cols = [c for c in cols_to_keep if c in df.columns]
            
            df = df[final_cols]

            # Lưu file
            file_name = f"data/{symbol}.csv"
            df.to_csv(file_name, index=False, encoding='utf-8')
            print(f"-> Xong! Đã tạo file: {file_name}")
        else:
            print("Không có record nào để lưu.")

    except Exception as e:
        print(f"Lỗi: {e}")

# --- Chạy thử ---

fetch_and_save_csv("STB")