import requests
import pandas as pd
import mysql.connector
from datetime import datetime
import time

# --- CẤU HÌNH (QUAN TRỌNG: ĐIỀN ĐÚNG PASSWORD CỦA BẠN) ---
DB_CONFIG = {
    'user': 'python',
    'password': '12345',       # Nếu bạn dùng XAMPP mặc định thì để trống
    'host': 'localhost',
    'database': 'python'  # Tên database bạn đã tạo (theo ảnh cũ bạn gửi là 'python')
}

# Danh sách mã muốn lấy (Lấy từ 01/01/2024 đến nay)
WATCHLIST = [ "VND", "SSI", "VIC", "VNM", "PNJ", "MWG", "FPT", "GAS", "HPG", "MSN",

"BID", "CTG", "STB", "ACB", "VPB", "TCB", "MBB", "SHB", "EIB", "HDB",

"VJC", "SAB", "BVH", "REE", "PLX", "PVD", "POW", "SBT", "KDC", "DPM" ]
START_DATE = "01/01/2024"

def get_db_connection():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"❌ LỖI KẾT NỐI DATABASE: {err}")
        return None

def setup_database():
    """Xóa bảng cũ (nếu có) và tạo bảng mới sạch sẽ"""
    conn = get_db_connection()
    if not conn: return False
    
    cursor = conn.cursor()
    try:
        # 1. Xóa bảng cũ để làm lại từ đầu (Tránh lỗi linh tinh)
        cursor.execute("DROP TABLE IF EXISTS stock_history")
        
        # 2. Tạo bảng mới chuẩn chỉ
        sql_create = """
        CREATE TABLE stock_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            symbol VARCHAR(10) NOT NULL,
            trading_date DATE NOT NULL,
            open DECIMAL(10, 2),
            high DECIMAL(10, 2),
            low DECIMAL(10, 2),
            close DECIMAL(10, 2),
            volume BIGINT,
            UNIQUE KEY unique_idx (symbol, trading_date)
        );
        """
        cursor.execute(sql_create)
        print("✅ Đã tạo bảng 'stock_history' thành công!")
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Lỗi tạo bảng: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

def fetch_and_import(symbol):
    """Tải dữ liệu và nạp thẳng vào MySQL"""
    print(f"⏳ Đang xử lý mã: {symbol}...", end=" ")
    
    # 1. Gọi API CafeF
    url = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    params = {
        "Symbol": symbol,
        "StartDate": START_DATE,
        "EndDate": datetime.now().strftime("%m/%d/%Y"),
        "PageIndex": 1,
        "PageSize": 10000, 
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        data = resp.json()
        
        records = []
        if isinstance(data, dict) and "Data" in data and "Data" in data["Data"]:
            records = data["Data"]["Data"]
            
        if not records:
            print("❌ Không có dữ liệu trên CafeF.")
            return

        # 2. Xử lý dữ liệu
        data_to_insert = []
        for item in records:
            try:
                # Parse ngày: 24/11/2024 -> 2024-11-24
                date_str = item['Ngay']
                py_date = datetime.strptime(date_str, "%d/%m/%Y")
                
                # Parse số (xử lý dấu phẩy)
                def clean(val):
                    return float(str(val).replace(',', ''))
                
                op = clean(item['GiaMoCua'])
                hi = clean(item['GiaCaoNhat'])
                lo = clean(item['GiaThapNhat'])
                cl = clean(item['GiaDongCua'])
                vol = int(clean(item['KhoiLuongKhopLenh']))
                
                # Sửa lỗi Close = 0 (cho ngày hiện tại)
                if cl == 0:
                    # Nếu có cột giá điều chỉnh thì dùng, không thì lấy trung bình
                    if 'GiaDieuChinh' in item:
                        cl = clean(item['GiaDieuChinh'])
                    if cl == 0: 
                        cl = (hi + lo) / 2
                data_to_insert.append((symbol, py_date.strftime('%Y-%m-%d'), op, hi, lo, cl, vol))
                
            except Exception as e:
                continue # Bỏ qua dòng lỗi

        # 3. Chèn vào MySQL
        if data_to_insert:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            sql = """
            INSERT IGNORE INTO stock_history (symbol, trading_date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(sql, data_to_insert)
            conn.commit()
            cursor.close()
            conn.close()
            print(f"✅ Đã thêm {len(data_to_insert)} dòng.")
        else:
            print("⚠️ Dữ liệu rỗng sau khi xử lý.")

    except Exception as e:
        print(f"❌ Lỗi: {e}")

# --- CHẠY CHƯƠNG TRÌNH ---
if __name__ == "__main__":
    print("=== BẮT ĐẦU RESET VÀ CẬP NHẬT DỮ LIỆU ===")
    
    # Bước 1: Thiết lập DB
    if setup_database():
        # Bước 2: Chạy vòng lặp lấy dữ liệu
        for sym in WATCHLIST:
            fetch_and_import(sym)
            time.sleep(1) # Nghỉ 1 xíu để không bị chặn IP
            
    print("\n=== HOÀN TẤT! HÃY KIỂM TRA DATABASE ===")