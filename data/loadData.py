import requests
import pandas as pd
from sqlalchemy import create_engine, text
import time
import random

# --- 1. CẤU HÌNH ---
# Sửa mật khẩu ở đây
DB_CONN_STR = 'mysql+pymysql://root:K123456789#@localhost/qlck'
db_engine = create_engine(DB_CONN_STR)

# Danh sách VN30 (30 mã lớn nhất thị trường) - Bạn có thể thêm bớt tùy ý
# Không nên chạy hết 1600 mã ngay lập tức vì CafeF sẽ khóa IP của bạn nếu tải quá nhanh
DANH_SACH_MA = [
    "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG",
    "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB",
    "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
]

def ensure_stock_exists(symbol):
    """Tạo mã trong bảng stocks nếu chưa có"""
    sql = text("""
        INSERT IGNORE INTO stocks (symbol, company_name, exchange, sector, is_active)
        VALUES (:symbol, :name, 'HOSE', 'VN30', 1)
    """)
    with db_engine.connect() as conn:
        conn.execute(sql, {"symbol": symbol, "name": f"Công ty {symbol}"})
        conn.commit()

def crawl_and_save(symbol):
    print(f"-> Đang xử lý: {symbol}...", end=" ")
    
    # 1. Đảm bảo mã tồn tại trong bảng stocks
    ensure_stock_exists(symbol)

    # 2. Gọi API CafeF
    url = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    params = {
        "Symbol": symbol,
        "StartDate": "01/01/2020", # Lấy dữ liệu từ 2020
        "EndDate": pd.Timestamp.now().strftime("%d/%m/%Y"),
        "PageIndex": 1,
        "PageSize": 10000,
    }
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        
        if "Data" not in data or "Data" not in data["Data"]:
            print("❌ Lỗi: Không có dữ liệu!")
            return

        # 3. Chuyển thành DataFrame
        df = pd.DataFrame(data["Data"]["Data"])
        
        # 4. Đổi tên cột và định dạng
        rename_map = {
            "Ngay": "timestamp", "GiaMoCua": "open", "GiaCaoNhat": "high",
            "GiaThapNhat": "low", "GiaDongCua": "close", "KhoiLuongKhopLenh": "volume"
        }
        df.rename(columns=rename_map, inplace=True)
        df['symbol'] = symbol
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='%d/%m/%Y')
        
        # Lọc cột
        final_df = df[['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']]

        # 5. Đẩy thẳng vào MySQL (KHÔNG LƯU FILE CSV)
        final_df.to_sql('market_candles', con=db_engine, if_exists='append', index=False, chunksize=1000)
        print(f"✅ Đã nạp {len(final_df)} dòng.")

    except Exception as e:
        if "Duplicate entry" in str(e):
            print("⚠️ Đã có rồi.")
        else:
            print(f"❌ Lỗi: {e}")

# --- CHẠY VÒNG LẶP ---
if __name__ == "__main__":
    print(f"Bắt đầu tải dữ liệu cho {len(DANH_SACH_MA)} mã VN30...")
    
    for ma in DANH_SACH_MA:
        crawl_and_save(ma)
        
        # QUAN TRỌNG: Nghỉ 1-3 giây giữa các lần tải để không bị CafeF chặn IP
        time.sleep(random.uniform(1, 3))
        
    print("\n=== HOÀN TẤT TOÀN BỘ ===")