import requests
import time
from datetime import datetime
import mysql.connector

# --- CẤU HÌNH DATABASE ---
DB_CONFIG = {
    'user': 'root',       
    'password': '123456',       
    'host': 'localhost',
    'database': 'python', 
    'raise_on_warnings': True,
    'use_pure': True  # FIX 1: Sử dụng pure Python driver để tránh bug C ext
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://s.cafef.vn/"
}

def convert_date_format(date_str):
    """Chuyển đổi dd/mm/yyyy sang yyyy-mm-dd cho MySQL"""
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        print(f"   Parsed date: {dt}")  # Debug: In ra ngày đã parse
        return dt.strftime("%Y-%m-%d")
    except ValueError as ve:
        print(f"   Lỗi parse ngày: {date_str} - {ve}")
        return None

def save_to_db(symbol, data_list):
    if not data_list:
        print(f"-> {symbol}: Không lấy được dữ liệu nào từ API.")
        return

    conn = None
    cursor = None  # Khai báo cursor ở đây để finally đóng đúng
    try:
        print(f"   Kết nối DB cho {symbol}...")  # Debug
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            print("   Kết nối DB thành công!")
        
        cursor = conn.cursor(buffered=True)  # FIX 2: buffered=True để fetch hết result nếu có

        # --- SQL: Loại bỏ ; ở cuối để an toàn ---
        sql = """
            INSERT INTO stock_history (symbol, date, open, high, low, close, volume, adjusted_close)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) AS new_data
            ON DUPLICATE KEY UPDATE
            open   = new_data.open,
            high   = new_data.high,
            low    = new_data.low,
            close  = new_data.close,
            volume = new_data.volume,
            adjusted_close = new_data.adjusted_close
        """  # Không có ; ở cuối

        val_list = []
        for row in data_list:
            sql_date = convert_date_format(row['date'])
            if sql_date:
                val = (
                    symbol, 
                    sql_date, 
                    row['open'], 
                    row['high'], 
                    row['low'], 
                    row['close'], 
                    row['volume'],
                    row['adjusted_close']
                )
                val_list.append(val)
                print(f"   Dữ liệu sẽ lưu: {val}")  # Debug: In dữ liệu trước insert
            else:
                print(f"   [WARN] Lỗi ngày tháng: {row['date']}")

        if val_list:
            try:
                cursor.executemany(sql, val_list)
                conn.commit()
                print(f"-> Đã lưu/cập nhật {cursor.rowcount} bản ghi cho mã {symbol}")
            except mysql.connector.Error as err:
                print(f"Lỗi MySQL ({symbol}) KHI INSERT: {err}")
                if val_list:
                    print(f"Dữ liệu mẫu đang gửi: {val_list[0]}")
        else:
            print(f"-> {symbol}: Không có dữ liệu hợp lệ để lưu (kiểm tra lại format ngày).")
        
    except mysql.connector.Error as err:
        print(f"Lỗi Kết nối MySQL ({symbol}): {err}")
    finally:
        if cursor:
            cursor.close()  # FIX 3: Đóng cursor trước khi đóng conn
        if conn and conn.is_connected():
            conn.close()
            print("   Đóng kết nối DB.")

def get_price_history(symbol, days=365):
    url = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    params = {"Symbol": symbol, "PageIndex": 1, "PageSize": days}
    
    try:
        print(f"   Gửi request cho {symbol}...")  # Debug
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        print(f"   Status code: {r.status_code}")
        if r.status_code != 200:
            print(f"   Lỗi HTTP: {r.text}")
            return []
        
        data = r.json()
        print(f"   Dữ liệu JSON: {data}")  # Debug: In JSON ngắn gọn
        
        if "Data" in data and "Data" in data["Data"] and data["Data"]["Data"]:
            raw_data = data["Data"]["Data"]
            print(f"   Số bản ghi raw: {len(raw_data)}")  # Debug
            result = []
            
            for row in raw_data:
                # --- Xử lý Volume ---
                vol = 0
                keys = ["KhoiLuongKhopLenh"]
                for k in keys:
                    if k in row and row[k] is not None:
                        try:
                            v_str = str(row[k]).replace('.', '').replace(',', '')
                            if v_str.isdigit():
                                val = int(v_str)
                                if val > 0:
                                    vol = val
                                    break
                        except Exception as e:
                            print(f"   Lỗi parse volume {k}: {e}")
                
                if vol == 0:
                    for k, v in row.items():
                        if ("Volume" in k or "KL" in k) and isinstance(v, (int, float, str)):
                            try:
                                v_str = str(v).replace('.', '').replace(',', '')
                                if v_str.isdigit():
                                    v_clean = int(v_str)
                                    if v_clean > 0:
                                        vol = v_clean
                                        break
                            except Exception as e:
                                print(f"   Lỗi parse fallback volume {k}: {e}")

                # --- XỬ LÝ GIÁ ---
                def parse_cafef_price(raw_val):
                    if raw_val is None: return 0.0
                    try:
                        s = str(raw_val)
                        if "," in s and "." in s: 
                            s = s.replace(",", "")
                        elif "," in s:
                            s = s.replace(",", ".")
                        return float(s)
                    except Exception as e:
                        print(f"   Lỗi parse giá: {raw_val} - {e}")
                        return 0.0

                o = parse_cafef_price(row.get("GiaMoCua")) * 1000
                h = parse_cafef_price(row.get("GiaCaoNhat")) * 1000
                l = parse_cafef_price(row.get("GiaThapNhat")) * 1000
                c = parse_cafef_price(row.get("GiaDongCua")) * 1000
                adj = parse_cafef_price(row.get("GiaDieuChinh")) * 1000

                result.append({
                    "date": row["Ngay"], 
                    "open": "{:.2f}".format(o),   
                    "high": "{:.2f}".format(h),
                    "low":  "{:.2f}".format(l),
                    "close":"{:.2f}".format(c),
                    "volume": vol,
                    "adjusted_close": "{:.2f}".format(adj)
                })
            return result
        else:
            print("   Không có 'Data' hợp lệ trong JSON.")
    except Exception as e:
        print(f" Lỗi API {symbol}: {e}")
    return []

def scan_all_symbols(symbol_list):
    print(f"Bắt đầu lấy dữ liệu cho {len(symbol_list)} mã...")
    
    for symbol in symbol_list:
        print(f"Đang xử lý: {symbol}...")
        
        data = get_price_history(symbol, days=365)
        
        if data:
            print(f"   Số bản ghi parsed: {len(data)}")  # Debug
            save_to_db(symbol, data)
        else:
            print(f"-> Không có dữ liệu cho {symbol}")
        
        time.sleep(1)

if __name__ == "__main__":
    list_ck = ["ACB", "BID", "BVH", "CTG", "FPT", "GAS", "HPG", "MBB", "MSN", "MWG", 
               "NVL", "PDR", "PLX", "PNJ", "POW", "SAB", "SSI", "STB", "TCB", "TPB", 
               "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE","DPM"]
    
    scan_all_symbols(list_ck)