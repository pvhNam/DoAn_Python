import mysql.connector
import numpy as np
import pandas as pd
import joblib
import os
import time
import warnings

# Tắt các cảnh báo hệ thống không cần thiết
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
warnings.filterwarnings('ignore')

# Thư viện AI
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

# Cấu hình kết nối database
DB_CONFIG = {
    'user': 'root',       
    'password': '123456',       
    'host': 'localhost',
    'database': 'python' 
}

# Hàm tính toán các chỉ báo kỹ thuật
def add_technical_indicators(df):
    # Tính RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Tính MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    
    # Tính Bollinger Bands
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['STD20'] = df['close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    
    # Loại bỏ các dòng bị thiếu dữ liệu do quá trình tính toán chỉ báo
    df.dropna(inplace=True)
    return df

# Hàm huấn luyện model cho từng mã cổ phiếu (Cập nhật logic Walk-forward 5 bước)
def train_model_for_symbol(symbol):
    conn = None
    try:
        # 1. Lấy TOÀN BỘ dữ liệu lịch sử ngay từ đầu
        conn = mysql.connector.connect(**DB_CONFIG)
        query = f"SELECT date, close, volume FROM stock_history WHERE symbol = '{symbol}' ORDER BY date ASC"
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df_full = pd.read_sql(query, conn)
        
        # Thêm chỉ báo kỹ thuật
        df_full = add_technical_indicators(df_full)
        
        total_rows = len(df_full)
        steps = 5       
        step_size = 30   #  Mỗi lần tăng thêm 30 ngày 
        look_back = 60   # Số phiên nhìn lại để dự đoán
        
        # Kiểm tra dữ liệu có đủ tối thiểu không (5 * 30 + 60 = 210 dòng)
        if total_rows < (steps * step_size) + look_back:
            print(f" Bỏ qua mã {symbol}: Dữ liệu ({total_rows} dòng) quá ít để train 5 bước.")
            return

        print(f" Bắt đầu chuỗi huấn luyện Walk-forward cho {symbol} (Tổng data: {total_rows} dòng)")

        # Tạo thư mục models_ai nếu chưa có
        if not os.path.exists('models_ai'):
            os.makedirs('models_ai')

        # 2. VÒNG LẶP TRAIN 5 LẦN
        for i in range(steps):
            # Tính toán lượng dữ liệu cần dùng cho lần lặp này
            rows_to_take = total_rows - ((steps - 1 - i) * step_size)
            
            # Cắt DataFrame
            df_current = df_full.iloc[:rows_to_take]
            
            print(f"   ► [Lần {i+1}/{steps}] Training với {len(df_current)} ngày dữ liệu...")

            # Chọn features
            features = ['close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
            data = df_current[features].values
            
            # Chuẩn hóa
            scaler = MinMaxScaler(feature_range=(0, 1))
            scaled_data = scaler.fit_transform(data)
            
            # Tạo Sliding Window
            X_train, y_train = [], []
            if len(scaled_data) <= look_back: continue

            for j in range(look_back, len(scaled_data)):
                X_train.append(scaled_data[j-look_back:j])
                y_train.append(scaled_data[j, 0]) 
            
            X_train, y_train = np.array(X_train), np.array(y_train)
            
            # Cấu trúc mạng LSTM
            model = Sequential()
            model.add(LSTM(units=50, return_sequences=True, input_shape=(X_train.shape[1], X_train.shape[2])))
            model.add(Dropout(0.2))
            model.add(LSTM(units=50, return_sequences=False))
            model.add(Dropout(0.2))
            model.add(Dense(units=1))
            
            model.compile(optimizer='adam', loss='mean_squared_error')
            
            model.fit(X_train, y_train, epochs=30, batch_size=32, verbose=0) 
            
            # Lưu model từng bước
            model_save_path = f'models_ai/{symbol}_step{i+1}.keras'
            model.save(model_save_path)
            
            # Lưu model & scaler cuối cùng 
            if i == steps - 1:
                model.save(f'models_ai/{symbol}_lstm.keras')
                joblib.dump(scaler, f'models_ai/{symbol}_scaler.pkl')

        print(f" Đã hoàn tất huấn luyện cho mã {symbol}")
        
    except Exception as e:
        print(f" Lỗi khi train mã {symbol}: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()

# Chạy chương trình chính
if __name__ == "__main__":
    print("=== HỆ THỐNG HUẤN LUYỆN AI CHỨNG KHOÁN (WALK-FORWARD) ===")
    
    try:
        # Kết nối database để lấy danh sách mã chứng khoán
        print("Đang quét danh sách cổ phiếu trong database...")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM stock_history")
        rows = cursor.fetchall()
        conn.close()
        
        list_ck = [row[0] for row in rows]
        
        if not list_ck:
            print(" LỖI: Database trống! Vui lòng chạy '1ydata.py' trước.")
            exit()
            
        print(f"Tìm thấy {len(list_ck)} mã cổ phiếu: {list_ck}")
        print("--------------------------------------------------")

        start_time = time.time()
        
        for idx, symbol in enumerate(list_ck):
            print(f"\n[{idx+1}/{len(list_ck)}] Đang xử lý mã: {symbol}")
            train_model_for_symbol(symbol)
             
        total_duration = time.time() - start_time
        
        print("\n==================================================")
        print(f"HOÀN TẤT HUẤN LUYỆN TOÀN BỘ THỊ TRƯỜNG!")
        print(f"Tổng thời gian: {total_duration:.2f} giây")
        print("==================================================")

    except Exception as e:
        print(f" Lỗi kết nối Database: {e}")