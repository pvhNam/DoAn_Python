import mysql.connector
import numpy as np
import pandas as pd
import joblib
import os
import time

# Thư viện AI & Xử lý dữ liệu
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

# --- CẤU HÌNH DATABASE (Phải khớp với database.py của bạn) ---
DB_CONFIG = {
    'user': 'python',       
    'password': '12345',       
    'host': 'localhost',
    'database': 'python' 
}

# --- HÀM TÍNH CHỈ BÁO KỸ THUẬT (Giống analysis.py) ---
def add_technical_indicators(df):
    # 1. RSI (Relative Strength Index)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # 2. MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    
    # 3. Bollinger Bands
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['STD20'] = df['close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    
    # Xóa các dòng NaN (do quá trình tính toán chỉ báo tạo ra)
    df.dropna(inplace=True)
    return df

# --- HÀM HUẤN LUYỆN CHO 1 MÃ ---
def train_model_for_symbol(symbol):
    try:
        # 1. Lấy dữ liệu từ Database
        conn = mysql.connector.connect(**DB_CONFIG)
        query = f"SELECT date, close, volume FROM stock_history WHERE symbol = '{symbol}' ORDER BY date ASC"
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Kiểm tra dữ liệu
        if len(df) < 100:
            print(f"   ⚠️ Bỏ qua: Dữ liệu quá ít ({len(df)} dòng)")
            return

        # 2. Thêm chỉ báo kỹ thuật
        df = add_technical_indicators(df)
        
        # 3. Chọn các cột dữ liệu để AI học (Features)
        features = ['close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
        data = df[features].values
        
        # 4. Chuẩn hóa dữ liệu về khoảng [0, 1] (Bắt buộc với LSTM)
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data)
        
        # 5. Tạo dữ liệu Sliding Window 
        # (Nhìn 60 ngày quá khứ -> Dự đoán giá đóng cửa ngày tiếp theo)
        X_train, y_train = [], []
        look_back = 60
        
        if len(scaled_data) <= look_back:
            print("   ⚠️ Bỏ qua: Không đủ dữ liệu sau khi cắt window")
            return

        for i in range(look_back, len(scaled_data)):
            X_train.append(scaled_data[i-look_back:i]) # Lấy 60 dòng quá khứ (cả 6 cột)
            y_train.append(scaled_data[i, 0])          # Target: Cột Close (index 0)
            
        X_train, y_train = np.array(X_train), np.array(y_train)
        
        # 6. Xây dựng mô hình LSTM
        model = Sequential()
        
        # Layer 1: LSTM với return_sequences=True (để nối tiếp layer sau)
        model.add(LSTM(units=50, return_sequences=True, input_shape=(X_train.shape[1], X_train.shape[2])))
        model.add(Dropout(0.2)) # Tránh học vẹt (Overfitting)
        
        # Layer 2: LSTM cuối cùng
        model.add(LSTM(units=50, return_sequences=False))
        model.add(Dropout(0.2))
        
        # Output Layer: Dự đoán 1 giá trị (Giá Close)
        model.add(Dense(units=1)) 
        
        model.compile(optimizer='adam', loss='mean_squared_error')
        
        # 7. Bắt đầu Train
        print(f"   🚀 Đang train model (Epochs=5)...")
        # epochs=5 để chạy nhanh, muốn xịn hơn thì tăng lên 20 hoặc 50
        model.fit(X_train, y_train, epochs=50, batch_size=32, verbose=0) 
        
        # 8. Lưu Model và Scaler
        if not os.path.exists('models_ai'):
            os.makedirs('models_ai')
            
        model.save(f'models_ai/{symbol}_lstm.keras')
        joblib.dump(scaler, f'models_ai/{symbol}_scaler.pkl')
        
        print(f"   ✅ Đã lưu thành công: models_ai/{symbol}_lstm.keras")
        
    except Exception as e:
        print(f"   ❌ Lỗi khi train mã {symbol}: {e}")

# --- CHẠY CHƯƠNG TRÌNH ---
if __name__ == "__main__":
    print("\n==================================================")
    print("🤖 HỆ THỐNG HUẤN LUYỆN AI CHỨNG KHOÁN (AUTO MODE)")
    print("==================================================\n")
    
    try:
        # 1. Tự động lấy danh sách mã có trong Database
        print("⏳ Đang quét danh sách cổ phiếu trong Database...")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM stock_history")
        rows = cursor.fetchall()
        conn.close()
        
        # Chuyển thành list ['HPG', 'FPT', ...]
        list_ck = [row[0] for row in rows]
        
        if not list_ck:
            print("❌ LỖI: Database trống trơn! Chưa có dữ liệu lịch sử.")
            print("👉 Vui lòng chạy file '1ydata.py' trước để lấy dữ liệu.")
            exit()
            
        print(f"📋 Tìm thấy {len(list_ck)} mã cổ phiếu: {list_ck}")
        print("--------------------------------------------------")

        # 2. Vòng lặp Train từng mã
        start_time = time.time()
        
        for idx, symbol in enumerate(list_ck):
            print(f"\n[{idx+1}/{len(list_ck)}] Đang xử lý mã: {symbol}")
            train_model_for_symbol(symbol)
            
        end_time = time.time()
        duration = end_time - start_time
        
        print("\n==================================================")
        print(f"🎉 HOÀN TẤT HUẤN LUYỆN TOÀN BỘ THỊ TRƯỜNG!")
        print(f"⏱️ Tổng thời gian: {duration:.2f} giây")
        print("==================================================")

    except Exception as e:
        print(f"❌ Lỗi kết nối Database: {e}")