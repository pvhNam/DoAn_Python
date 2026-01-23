import mysql.connector
import numpy as np
import pandas as pd
import joblib
import os
import time
import json
import warnings

# Tắt các cảnh báo hệ thống không cần thiết
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
warnings.filterwarnings('ignore')

# Thư viện AI
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from ai_models import StockRNN  # Class RNN bạn đã tạo ở bước trước

# --- CẤU HÌNH DATABASE ---
DB_CONFIG = {
    'user': 'root',       
    'password': '123456',       
    'host': 'localhost',
    'database': 'python' 
}

# --- HÀM TÍNH CHỈ BÁO KỸ THUẬT ---
def add_technical_indicators(df):
    # 1. RSI
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
    
    df.fillna(0, inplace=True)
    return df

def train_model_for_symbol(symbol):
    conn = None
    try:
        # 1. Lấy dữ liệu từ Database
        conn = mysql.connector.connect(**DB_CONFIG)
        query = f"SELECT date, close, volume FROM stock_history WHERE symbol = '{symbol}' ORDER BY date ASC"
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            df = pd.read_sql(query, conn)
        
        if len(df) < 100:
            print(f"   ⚠️ Bỏ qua: Dữ liệu quá ít ({len(df)} bản ghi)")
            return

        # 2. Xử lý dữ liệu
        df = add_technical_indicators(df)
        features = ['close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
        data = df[features].values
        
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data)
        
        X_train, y_train = [], []
        look_back = 60
        
        if len(scaled_data) <= look_back: return

        for i in range(look_back, len(scaled_data)):
            X_train.append(scaled_data[i-look_back:i])
            y_train.append(scaled_data[i, 0])
            
        X_train, y_train = np.array(X_train), np.array(y_train)
        
        # Tạo thư mục lưu model
        if not os.path.exists('models_ai'): os.makedirs('models_ai')

        # =========================================================
        # MODEL 1: LSTM (Long Short-Term Memory)
        # =========================================================
        print(f"   🚀 [LSTM] Đang train...")
        start_lstm = time.time()
        
        model_lstm = Sequential()
        model_lstm.add(Input(shape=(X_train.shape[1], X_train.shape[2])))
        model_lstm.add(LSTM(50, return_sequences=True))
        model_lstm.add(Dropout(0.2))
        model_lstm.add(LSTM(50, return_sequences=False))
        model_lstm.add(Dropout(0.2))
        model_lstm.add(Dense(1))
        
        # Thêm metrics=['mae'] để đo sai số tuyệt đối
        model_lstm.compile(optimizer='adam', loss='mean_squared_error', metrics=['mae'])
        model_lstm.fit(X_train, y_train, epochs=5, batch_size=32, verbose=0)
        
        time_lstm = time.time() - start_lstm
        
        # Đánh giá lại model
        loss_lstm, mae_lstm = model_lstm.evaluate(X_train, y_train, verbose=0)
        
        model_lstm.save(f'models_ai/{symbol}_lstm.keras')
        joblib.dump(scaler, f'models_ai/{symbol}_scaler.pkl') # Scaler dùng chung

        # =========================================================
        # MODEL 2: RNN (Recurrent Neural Network)
        # =========================================================
        print(f"   🌊 [RNN] Đang train...")
        start_rnn = time.time()
        
        rnn_agent = StockRNN(symbol)
        # Chúng ta cần gọi hàm build_model và compile bên trong class,
        # Sau đó fit thủ công để đo thời gian chính xác tại đây
        rnn_agent.build_model((X_train.shape[1], X_train.shape[2]))
        
        # Compile lại với metric MAE để so sánh công bằng
        rnn_agent.model.compile(optimizer='adam', loss='mean_squared_error', metrics=['mae'])
        rnn_agent.model.fit(X_train, y_train, epochs=5, batch_size=32, verbose=0)
        
        time_rnn = time.time() - start_rnn
        loss_rnn, mae_rnn = rnn_agent.model.evaluate(X_train, y_train, verbose=0)
        
        rnn_agent.save_model()

        # =========================================================
        # LƯU KẾT QUẢ SO SÁNH (JSON)
        # =========================================================
        stats = {
            "LSTM": {
                "loss_mse": round(loss_lstm, 6),
                "mae": round(mae_lstm, 6),
                "time": round(time_lstm, 2)
            },
            "RNN": {
                "loss_mse": round(loss_rnn, 6),
                "mae": round(mae_rnn, 6),
                "time": round(time_rnn, 2)
            },
            # Winner dựa trên Loss (MSE) thấp nhất
            "winner": "LSTM" if loss_lstm < loss_rnn else "RNN",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(f'models_ai/{symbol}_comparison.json', 'w') as f:
            json.dump(stats, f, indent=4)
            
        print(f"   📊 Kết quả: LSTM(Loss={loss_lstm:.5f}) vs RNN(Loss={loss_rnn:.5f}) => Tốt hơn: {stats['winner']}")

    except Exception as e:
        print(f"   ❌ Lỗi khi train mã {symbol}: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()

if __name__ == "__main__":
    print("\n==================================================")
    print("🤖 HỆ THỐNG HUẤN LUYỆN & SO SÁNH AI (LSTM vs RNN)")
    print("==================================================\n")
    
    try:
        print("⏳ Đang quét danh sách cổ phiếu trong Database...")
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM stock_history")
        rows = cursor.fetchall()
        conn.close()
        
        list_ck = [row[0] for row in rows]
        
        if not list_ck:
            print("❌ LỖI: Database trống trơn! Vui lòng chạy '1ydata.py' trước.")
            exit()
            
        print(f"📋 Tìm thấy {len(list_ck)} mã cổ phiếu.")
        print("--------------------------------------------------")

        total_start = time.time()
        
        for idx, symbol in enumerate(list_ck):
            print(f"\n[{idx+1}/{len(list_ck)}] Đang xử lý mã: {symbol}")
            train_model_for_symbol(symbol)
            
        total_duration = time.time() - total_start
        
        print("\n==================================================")
        print(f"🎉 HOÀN TẤT HUẤN LUYỆN TOÀN BỘ ({total_duration:.2f}s)")
        print("==================================================")
        
    except Exception as e:
        print(f"❌ Lỗi chương trình chính: {e}")