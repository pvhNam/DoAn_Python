import pandas as pd
import os
from sqlalchemy import create_engine, text

# --- 1. CẤU HÌNH KẾT NỐI (Sửa password của bạn) ---
# Lưu ý: Sửa '123456' thành mật khẩu MySQL của bạn
db_connection_str = 'mysql+pymysql://root:K123456789#@localhost/qlck'
db_engine = create_engine(db_connection_str)

def import_csv_files():
    # Kiểm tra xem thư mục data có tồn tại không
    folder_path = 'data'
    if not os.path.exists(folder_path):
        print("Lỗi: Không tìm thấy thư mục 'data'!")
        return

    # Lấy danh sách tất cả các file .csv trong thư mục data
    all_files = [f for f in os.listdir(folder_path) if f.endswith('.csv')]
    
    print(f"Tìm thấy {len(all_files)} file CSV: {all_files}")

    for filename in all_files:
        # Lấy tên mã từ tên file (Ví dụ: 'HPG.csv' -> symbol là 'HPG')
        symbol = filename.replace('.csv', '')
        file_path = os.path.join(folder_path, filename)
        
        print(f"\n--- Đang xử lý file: {filename} (Mã: {symbol}) ---")

        try:
            # BƯỚC 1: Tạo mã trong bảng 'stocks' trước (Bắt buộc)
            # Nếu không tạo dòng này, MySQL sẽ báo lỗi vì không biết HPG là gì
            sql_create_stock = text("""
                INSERT IGNORE INTO stocks (symbol, company_name, exchange, sector, is_active)
                VALUES (:symbol, :name, 'HOSE', 'Unknown', 1)
            """)
            
            with db_engine.connect() as conn:
                conn.execute(sql_create_stock, {"symbol": symbol, "name": f"Công ty {symbol}"})
                conn.commit()

            # BƯỚC 2: Đọc file CSV và đẩy vào bảng 'market_candles'
            df = pd.read_csv(file_path)

            # Chuẩn hóa tên cột
            df['symbol'] = symbol
            # Đổi tên cột trong CSV cho khớp với Database
            rename_map = {
                'Date': 'timestamp', 'Open': 'open', 'High': 'high',
                'Low': 'low', 'Close': 'close', 'Volume': 'volume'
            }
            # Nếu file CSV của bạn đang dùng tên cột tiếng Việt (Ngay, GiaMoCua...) thì dùng map này:
            # rename_map = {'Ngay': 'timestamp', 'GiaMoCua': 'open', ...} 
            
            # Kiểm tra xem file CSV đang dùng tiếng Anh hay tiếng Việt để rename cho đúng
            if 'Date' in df.columns:
                df.rename(columns=rename_map, inplace=True)
            elif 'Ngay' in df.columns: # Trường hợp file cũ tải về bằng tiếng Việt
                 df.rename(columns={
                    "Ngay": "timestamp", "GiaMoCua": "open", "GiaCaoNhat": "high",
                    "GiaThapNhat": "low", "GiaDongCua": "close", "KhoiLuongKhopLenh": "volume"
                }, inplace=True)

            # Format ngày tháng
            df['timestamp'] = pd.to_datetime(df['timestamp'], dayfirst=True) # dayfirst=True để hiểu đúng dd/mm/yyyy

            # Chỉ lấy các cột cần thiết
            cols_to_db = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
            df_ready = df[cols_to_db]

            # Đẩy vào MySQL
            df_ready.to_sql('market_candles', con=db_engine, if_exists='append', index=False, chunksize=1000)
            print(f"-> Đã nhập thành công {len(df_ready)} dòng dữ liệu!")

        except Exception as e:
            if "Duplicate entry" in str(e):
                print(f"-> Dữ liệu của {symbol} đã có rồi, bỏ qua.")
            else:
                print(f"-> Lỗi: {e}")

# --- CHẠY ---
if __name__ == "__main__":
    import_csv_files()