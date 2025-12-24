import requests
import time
from datetime import datetime
import mysql.connector

# --- CẤU HÌNH DATABASE ---
DB_CONFIG = {
    'user': 'stock_admin',       # Thay bằng user của bạn
    'password': 'password123',       # Thay bằng pass của bạn
    'host': 'localhost',
    'database': 'python', # Tên database chứa bảng stock_history
    'raise_on_warnings': True
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://s.cafef.vn/"
}

def convert_date_format(date_str):
    """Chuyển đổi dd/mm/yyyy sang yyyy-mm-dd cho MySQL"""
    try:
        return datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None

def save_to_db(symbol, data_list):
    if not data_list:
        print(f"-> {symbol}: Không lấy được dữ liệu nào từ API.")
        return

    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()

        sql = """
            INSERT INTO stock_history (symbol, date, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s) AS new_data
            ON DUPLICATE KEY UPDATE
            open   = new_data.open,
            high   = new_data.high,
            low    = new_data.low,
            close  = new_data.close,
            volume = new_data.volume;
        """

        val_list = []
        for row in data_list:
            sql_date = convert_date_format(row['date'])
            if sql_date:
                # Dữ liệu lúc này là String format chuẩn, MySQL sẽ tự ép kiểu an toàn
                val = (
                    symbol, 
                    sql_date, 
                    row['open'], 
                    row['high'], 
                    row['low'], 
                    row['close'], 
                    row['volume']
                )
                val_list.append(val)
            else:
                # In ra nếu ngày lỗi (nguyên nhân ACB có thể bị 0 bản ghi)
                print(f"   [WARN] Lỗi ngày tháng: {row['date']}")

        if val_list:
            try:
                cursor.executemany(sql, val_list)
                conn.commit()
                print(f"-> Đã lưu/cập nhật {cursor.rowcount} bản ghi cho mã {symbol}")
            except mysql.connector.Error as err:
                # Nếu vẫn lỗi, in ra dòng dữ liệu đầu tiên để kiểm tra
                print(f"Lỗi MySQL ({symbol}) KHI INSERT: {err}")
                print(f"Dữ liệu mẫu đang gửi: {val_list[0]}")
        else:
            print(f"-> {symbol}: Không có dữ liệu hợp lệ để lưu (kiểm tra lại format ngày).")
        
    except mysql.connector.Error as err:
        print(f"Lỗi Kết nối MySQL ({symbol}): {err}")
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

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
                # --- Xử lý Volume ---
                vol = 0
                # (Giữ nguyên logic Volume của bạn vì nó đang ổn)
                keys = ["nmVolume", "nmTotalVolume", "KlgiaoDichKhopLenh", "TotalVolume", "Volume", "KLKhopLenh"]
                for k in keys:
                    if k in row and row[k] is not None:
                        try:
                            v_str = str(row[k]).split('.')[0]
                            v_clean = v_str.replace(",", "").replace(".", "")
                            if v_clean.isdigit():
                                val = int(v_clean)
                                if val > 0:
                                    vol = val
                                    break
                        except:
                            pass
                
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

                # --- XỬ LÝ GIÁ (FIX LỖI TRUNCATED) ---
                # Hàm con để ép mọi thứ thành số float thuần túy
                def parse_cafef_price(raw_val):
                    if raw_val is None: return 0.0
                    try:
                        # Xử lý trường hợp "1,234.5" hoặc "1.234,5" của VN
                        s = str(raw_val)
                        if "," in s and "." in s: 
                            s = s.replace(",", "") # Bỏ dấu phẩy hàng nghìn nếu có cả 2
                        elif "," in s:
                            s = s.replace(",", ".") # Nếu chỉ có phẩy, coi là dấu thập phân
                        return float(s)
                    except:
                        return 0.0

                # Lấy giá trị float, nhân 1000
                o = parse_cafef_price(row.get("GiaMoCua")) * 1000
                h = parse_cafef_price(row.get("GiaCaoNhat")) * 1000
                l = parse_cafef_price(row.get("GiaThapNhat")) * 1000
                c = parse_cafef_price(row.get("GiaDongCua")) * 1000

                # QUAN TRỌNG: Format thành chuỗi "12345.00" để MySQL không bao giờ hiểu nhầm
                result.append({
                    "date": row["Ngay"], 
                    "open": "{:.2f}".format(o),   # Chuyển thành String 2 số lẻ
                    "high": "{:.2f}".format(h),
                    "low":  "{:.2f}".format(l),
                    "close":"{:.2f}".format(c),
                    "volume": vol 
                })
            return result
    except Exception as e:
        print(f" Lỗi API {symbol}: {e}")
    return []

def scan_all_symbols(symbol_list):
    """Hàm chạy loop qua danh sách mã chứng khoán"""
    print(f"Bắt đầu lấy dữ liệu cho {len(symbol_list)} mã...")
    
    for symbol in symbol_list:
        print(f"Đang xử lý: {symbol}...")
        
        # 1. Lấy dữ liệu từ API
        data = get_price_history(symbol, days=5475) # Lấy 1 năm
        
        # 2. Lưu vào DB
        if data:
            save_to_db(symbol, data)
        else:
            print(f"-> Không có dữ liệu cho {symbol}")
            
        # 3. Sleep để tránh bị chặn IP
        time.sleep(1) # Nghỉ 1 giây giữa mỗi lần request

# --- CHẠY CHƯƠNG TRÌNH ---
if __name__ == "__main__":
    # Danh sách các mã cần lấy. 
    # Bạn có thể lấy danh sách này từ một file text, hoặc một bảng khác trong DB.
    # Dưới đây là ví dụ với VN30
    list_ck = ["ACB", "BID", "BVH", "CTG", "FPT", "GAS", "HPG", "MBB", "MSN", "MWG", 
               "NVL", "PDR", "PLX", "PNJ", "POW", "SAB", "SSI", "STB", "TCB", "TPB", 
               "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE","DPM"]
    
    # Nếu muốn thêm nhiều mã, hãy bổ sung vào list_ck
    scan_all_symbols(list_ck)