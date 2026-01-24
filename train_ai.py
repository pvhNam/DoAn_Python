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

# Cấu hình kết nối database
DB_CONFIG = {
    'user': 'stock_admin',       
    'password': 'password123',       
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

# Hàm huấn luyện model cho từng mã cổ phiếu
def train_model_for_symbol(symbol):
    try:
        # Lấy dữ liệu lịch sử từ database
        conn = mysql.connector.connect(**DB_CONFIG)
        query = f"SELECT date, close, volume FROM stock_history WHERE symbol = '{symbol}' ORDER BY date ASC"
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Nếu dữ liệu ít quá thì bỏ qua, không train được
        if len(df) < 100:
            print(f"Bỏ qua mã {symbol}: Dữ liệu quá ít ({len(df)} dòng)")
            return

        # Thêm các chỉ báo kỹ thuật vào dữ liệu
        df = add_technical_indicators(df)
        
        # Chọn các đặc trưng (features) đầu vào để model học
        features = ['close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
        data = df[features].values
        
        # Chuẩn hóa dữ liệu về khoảng 0-1 (bắt buộc đối với mạng LSTM)
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data)
        
        # Xử lý dữ liệu dạng chuỗi thời gian (Sliding Window)
        # Logic: Dùng 60 phiên quá khứ để dự đoán giá đóng cửa phiên tiếp theo
        X_train, y_train = [], []
        look_back = 60
        
        if len(scaled_data) <= look_back:
            print(f"Bỏ qua mã {symbol}: Không đủ dữ liệu sau khi cắt window")
            return

        for i in range(look_back, len(scaled_data)):
            X_train.append(scaled_data[i-look_back:i]) # Lấy 60 dòng quá khứ
            y_train.append(scaled_data[i, 0])          # Mục tiêu là cột Close (index 0)
            
        X_train, y_train = np.array(X_train), np.array(y_train)
        
        # Cấu trúc mạng LSTM
        model = Sequential()
        
        # Layer 1: LSTM có return_sequences=True để nối tiếp sang layer sau
        model.add(LSTM(units=50, return_sequences=True, input_shape=(X_train.shape[1], X_train.shape[2])))
        model.add(Dropout(0.2)) # Dùng Dropout để hạn chế học vẹt (overfitting)
        
        # Layer 2: LSTM cuối
        model.add(LSTM(units=50, return_sequences=False))
        model.add(Dropout(0.2))
        
        # Output Layer: Trả về 1 giá trị dự đoán (Close price)
        model.add(Dense(units=1)) 
        
        model.compile(optimizer='adam', loss='mean_squared_error')
        
        # Bắt đầu train
        print(f"Đang train model cho {symbol} (Epochs=200)...")
        model.fit(X_train, y_train, epochs=200, batch_size=32, verbose=0) 
        
        # Lưu model và scaler lại để dùng sau này
        if not os.path.exists('models_ai'):
            os.makedirs('models_ai')
            
        model.save(f'models_ai/{symbol}_lstm.keras')
        joblib.dump(scaler, f'models_ai/{symbol}_scaler.pkl')
        
        print(f"Đã lưu model: models_ai/{symbol}_lstm.keras")
        
    except Exception as e:
        print(f"Lỗi khi train mã {symbol}: {e}")

# Chạy chương trình chính
if __name__ == "__main__":
    print("He thong huan luyen AI chung khoan")
    
    try:
        # Kết nối database để lấy danh sách mã chứng khoán
        print("Đang quét danh sách cổ phiếu trong database...")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM stock_history")
        rows = cursor.fetchall()
        conn.close()
        
        # Chuyển kết quả query thành list
        list_ck = [row[0] for row in rows]
        
        if not list_ck:
            print("Lỗi: Database trống, chưa có dữ liệu lịch sử.")
            print("Vui lòng chạy file lấy dữ liệu trước.")
            exit()
            
        print(f"Tìm thấy {len(list_ck)} mã cổ phiếu.")

        # Bắt đầu vòng lặp train từng mã
        start_time = time.time()
        
        for idx, symbol in enumerate(list_ck):
            print(f"[{idx+1}/{len(list_ck)}] Đang xử lý mã: {symbol}")
            train_model_for_symbol(symbol)
            
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"Hoàn tất huấn luyện toàn bộ thị trường.")
        print(f"Tổng thời gian chạy: {duration:.2f} giây")

    except Exception as e:
        print(f"Lỗi kết nối database: {e}")