import mysql.connector
import numpy as np
import pandas as pd
import joblib
import os
import json
import warnings
from datetime import datetime, timedelta  # <--- 1. Thêm timedelta

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
warnings.filterwarnings('ignore')

from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from ai_models import StockRNN

DB_CONFIG = {
    'user': 'root', 'password': '123456',
    'host': 'localhost', 'database': 'python'
}
SPLIT_DATE = '2024-10-01' 

def add_technical_indicators(df):
    delta = df['adjusted_close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=30).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=30).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    ema12 = df['adjusted_close'].ewm(span=12, adjust=False).mean()
    ema26 = df['adjusted_close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['MA20'] = df['adjusted_close'].rolling(window=20).mean()
    df['STD20'] = df['adjusted_close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    df.fillna(0, inplace=True)
    return df

def train_backtest(symbol):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        query = f"SELECT date, adjusted_close, volume FROM stock_history WHERE symbol = '{symbol}' ORDER BY date ASC"
        df = pd.read_sql(query, conn)
        conn.close()

        # --- SỬA LỖI VÀ THÊM LOGIC 10 NĂM TẠI ĐÂY ---
        
        # 1. Xác định ngày kết thúc (Split date)
        split_date_obj = datetime.strptime(SPLIT_DATE, '%Y-%m-%d').date()
        
        # 2. Xác định ngày bắt đầu (10 năm trước)
        # 365 * 10 = 3650 ngày (xấp xỉ 10 năm)
        start_date_obj = split_date_obj - timedelta(days=365 * 10)

        print(f" ⏳ Lọc dữ liệu từ {start_date_obj} đến {split_date_obj} (10 năm)")

        # 3. Lọc dữ liệu: Lấy >= 10 năm trước VÀ < ngày split
        df_train = df[
            (df['date'] >= start_date_obj) & 
            (df['date'] < split_date_obj)
        ].copy()
        
        print(f" 📅 Dữ liệu thực tế train đến: {df_train['date'].iloc[-1]} (Tổng {len(df_train)} bản ghi)")

        if len(df_train) < 100: 
            print("⚠️ Dữ liệu quá ít để train!")
            return

        df_train = add_technical_indicators(df_train)
        features = ['adjusted_close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
        data = df_train[features].values
        
        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(data)
        
        X_train, y_train = [], []
        look_back = 60 

        for i in range(look_back, len(scaled_data)):
            X_train.append(scaled_data[i-look_back:i])
            y_train.append(scaled_data[i, 0])
            
        X_train, y_train = np.array(X_train), np.array(y_train)
        
        if not os.path.exists('models_backtest'): os.makedirs('models_backtest')

        # 1. Train LSTM
        print(f"   🚀 [LSTM] Training...")
        model_lstm = Sequential()
        model_lstm.add(Input(shape=(X_train.shape[1], X_train.shape[2])))
        model_lstm.add(LSTM(50, return_sequences=True))
        model_lstm.add(Dropout(0.2))
        model_lstm.add(LSTM(50, return_sequences=False))
        model_lstm.add(Dense(1))
        model_lstm.compile(optimizer='adam', loss='mean_squared_error')
        model_lstm.fit(X_train, y_train, epochs=5, batch_size=32, verbose=0)
        model_lstm.save(f'models_backtest/{symbol}_lstm.keras')

        # 2. Train RNN
        print(f"   🌊 [RNN] Training...")
        rnn = StockRNN(symbol)
        rnn.model_path = f'models_backtest/{symbol}_rnn.keras' 
        rnn.build_model((X_train.shape[1], X_train.shape[2]))
        rnn.train(X_train, y_train, epochs=5)
        rnn.save_model()
        
        joblib.dump(scaler, f'models_backtest/{symbol}_scaler.pkl')
        print(f"   ✅ Hoàn tất train cho {symbol}")

    except Exception as e:
        print(f"❌ Lỗi {symbol}: {e}")

if __name__ == "__main__":
    print(f"🛡️ CHẾ ĐỘ BACKTEST: Train 10 năm dữ liệu trước {SPLIT_DATE}")
    train_backtest('MBB')