import requests
import time
from datetime import datetime
import mysql.connector
import re  

DB_CONFIG = {
    'user': 'stock_admin',       
    'password': 'password123',       
    'host': 'localhost',
    'database': 'python', 
    'raise_on_warnings': True,
    'use_pure': True
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://s.cafef.vn/"
}

def convert_date_format(date_str):
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        return dt.strftime("%Y-%m-%d")
    except ValueError as ve:
        return None

def save_to_db(symbol, data_list):
    if not data_list:
        print(f"-> {symbol}: Không lấy được dữ liệu nào từ API.")
        return

    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(buffered=True)
        sql = """
            INSERT INTO stock_history (symbol, date, open, high, low, close, volume, adjusted_close, price_change, percent_change)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS new_data
            ON DUPLICATE KEY UPDATE
            open           = new_data.open,
            high           = new_data.high,
            low            = new_data.low,
            close          = new_data.close,
            volume         = new_data.volume,
            adjusted_close = new_data.adjusted_close,
            price_change   = new_data.price_change,
            percent_change = new_data.percent_change
        """

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
                    row['adjusted_close'],
                    row['change_raw'],     
                    row['percent_change']  
                )
                val_list.append(val)

        if val_list:
            try:
                cursor.executemany(sql, val_list)
                conn.commit()
                print(f"-> Đã lưu/cập nhật {cursor.rowcount} bản ghi cho mã {symbol}")
            except mysql.connector.Error as err:
                print(f"Lỗi MySQL ({symbol}) KHI INSERT: {err}")
        else:
            print(f"-> {symbol}: Không có dữ liệu hợp lệ để lưu.")
        
    except mysql.connector.Error as err:
        print(f"Lỗi Kết nối MySQL ({symbol}): {err}")
    finally:
        if cursor: cursor.close()
        if conn and conn.is_connected(): conn.close()

def get_price_history(symbol, days=1000):
    url = "https://s.cafef.vn/Ajax/PageNew/DataHistory/PriceHistory.ashx"
    params = {"Symbol": symbol, "PageIndex": 1, "PageSize": days}
    
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        
        if r.status_code != 200:
            print(f"   Lỗi HTTP: {r.text}")
            return []
        
        data = r.json()
        
        if "Data" in data and "Data" in data["Data"] and data["Data"]["Data"]:
            raw_data = data["Data"]["Data"]
            result = []
            

            pattern_percent = re.compile(r"\(([-+]?[0-9]*\.?[0-9]+)\s*%\)")

            for row in raw_data:
                vol = 0
                keys = ["KhoiLuongKhopLenh"]
                for k in keys:
                    if k in row and row[k] is not None:
                        try:
                            v_str = str(row[k]).replace('.', '').replace(',', '')
                            if v_str.isdigit() and int(v_str) > 0:
                                vol = int(v_str)
                                break
                        except: pass
                
                def parse_cafef_price(raw_val):
                    if raw_val is None: return 0.0
                    try:
                        s = str(raw_val)
                        if "," in s and "." in s: s = s.replace(",", "")
                        elif "," in s: s = s.replace(",", ".")
                        return float(s)
                    except: return 0.0

                o = parse_cafef_price(row.get("GiaMoCua")) * 1000
                h = parse_cafef_price(row.get("GiaCaoNhat")) * 1000
                l = parse_cafef_price(row.get("GiaThapNhat")) * 1000
                c = parse_cafef_price(row.get("GiaDongCua")) * 1000
                adj = parse_cafef_price(row.get("GiaDieuChinh")) * 1000
                
                change_raw = row.get("ThayDoi", "")
                if change_raw is None: change_raw = ""
                
                pct_change = 0.0
                if change_raw:
                    match = pattern_percent.search(str(change_raw))
                    if match:
                        try:
                            pct_change = float(match.group(1))
                        except:
                            pct_change = 0.0

                result.append({
                    "date": row["Ngay"], 
                    "open": "{:.2f}".format(o),   
                    "high": "{:.2f}".format(h),
                    "low":  "{:.2f}".format(l),
                    "close":"{:.2f}".format(c),
                    "volume": vol,
                    "adjusted_close": "{:.2f}".format(adj),
                    "change_raw": str(change_raw),   
                    "percent_change": pct_change      
                })
            return result
    except Exception as e:
        print(f" Lỗi API {symbol}: {e}")
    return []

def scan_all_symbols(symbol_list):
    print(f"Bắt đầu lấy dữ liệu cho {len(symbol_list)} mã...")
    
    for symbol in symbol_list:
        try:
            print(f"--------------------------------")
            print(f"Đang xử lý: {symbol}...")
            
            data = get_price_history(symbol, days=1000)
            
            if data:
                print(f"   -> Tìm thấy {len(data)} bản ghi. Đang lưu...")
                save_to_db(symbol, data)
            else:
                print(f"   -> [CẢNH BÁO] Không có dữ liệu cho {symbol}")
                
        except Exception as e:
            print(f"   -> [LỖI NGHIÊM TRỌNG] Mã {symbol} bị lỗi: {e}")
            print("   -> Bỏ qua, chuyển sang mã tiếp theo...")
            
        time.sleep(1)

    print("\n=== HOÀN TẤT QUÁ TRÌNH CẬP NHẬT ===")

if __name__ == "__main__":
    list_ck = ["ACB", "BID", "BVH", "CTG", "FPT", "GAS", "HPG", "MBB", "MSN", "MWG", 
               "NVL", "PDR", "PLX", "PNJ", "POW", "SAB", "SSI", "STB", "TCB", "TPB", 
               "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE","DPM"]
    
    scan_all_symbols(list_ck)