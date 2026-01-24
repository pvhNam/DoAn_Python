import mysql.connector
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import time
import math

# Thư viện AI & Thống kê
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_percentage_error
from statsmodels.tsa.arima.model import ARIMA
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, SimpleRNN, LSTM, Dropout
from tensorflow.keras.callbacks import EarlyStopping

# --- CẤU HÌNH ---
DB_CONFIG = {
    'user': 'root',       
    'password': '123456',       
    'host': 'localhost',
    'database': 'python' 
}
SYMBOL = "ACB"       
LOOK_BACK = 60       
EPOCHS = 200          # Set cao để Early Stopping tự xử lý
BATCH_SIZE = 32

# =============================================================================
# 1. HÀM TÍNH TOÁN CHỈ SỐ (Lấy logic từ train_ai.py)
# =============================================================================
def add_technical_indicators(df):
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    
    # Bollinger Bands
    df['MA20'] = df['close'].rolling(window=20).mean()
    df['STD20'] = df['close'].rolling(window=20).std()
    df['BB_Upper'] = df['MA20'] + (df['STD20'] * 2)
    df['BB_Lower'] = df['MA20'] - (df['STD20'] * 2)
    
    df.dropna(inplace=True) # Xóa dữ liệu NaN do tính toán
    return df

def get_data_full_features(symbol):
    print(f"--> Đang lấy dữ liệu {symbol} và tính toán chỉ báo...")
    conn = mysql.connector.connect(**DB_CONFIG)
    # Lấy thêm Volume
    query = f"SELECT date, close, volume FROM stock_history WHERE symbol = '{symbol}' ORDER BY date ASC"
    df = pd.read_sql(query, conn)
    conn.close()
    df['date'] = pd.to_datetime(df['date'])
    
    if len(df) < 200: return None, None
    
    # Thêm chỉ báo vào DataFrame
    df = add_technical_indicators(df)
    
    # Chọn 6 cột đặc trưng (Features)
    features = ['close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
    data_values = df[features].values
    dates = df['date'].values
    
    return data_values, dates

# =============================================================================
# 2. CHUẨN BỊ DỮ LIỆU ĐA BIẾN
# =============================================================================
def prepare_data_multivariate(data, look_back=60):
    X, y = [], []
    for i in range(look_back, len(data)):
        X.append(data[i-look_back:i]) # Lấy cả 6 cột của 60 ngày quá khứ
        y.append(data[i, 0])          # Chỉ dự đoán cột 0 (Close Price)
    return np.array(X), np.array(y)

# =============================================================================
# 3. XÂY DỰNG MODEL (CẤU TRÚC CHUẨN)
# =============================================================================
def build_and_train_model(model_type, X_train, y_train):
    print(f"\n[Training] {model_type} (Input: 6 Features)...")
    start_time = time.time()
    
    # Input shape: (60 ngày, 6 đặc trưng)
    input_shape = (X_train.shape[1], X_train.shape[2])
    
    model = Sequential()
    
    if model_type == 'RNN':
        model.add(SimpleRNN(50, return_sequences=True, input_shape=input_shape))
        model.add(Dropout(0.2))
        model.add(SimpleRNN(50, return_sequences=False))
        
    elif model_type == 'LSTM':
        # Cấu trúc 2 lớp LSTM (Stacked) giống hệt train_ai.py
        model.add(LSTM(50, return_sequences=True, input_shape=input_shape))
        model.add(Dropout(0.2))
        model.add(LSTM(50, return_sequences=False))
        
    model.add(Dropout(0.2))
    model.add(Dense(1)) # Output 1 giá trị Close
    
    model.compile(optimizer='adam', loss='mean_squared_error')
    
    # --- EARLY STOPPING (CẢNH SÁT) ---
    early_stop = EarlyStopping(
        monitor='val_loss', 
        patience=15,               # Kiên nhẫn 15 lần
        restore_best_weights=True  # Lấy lại bản tốt nhất
    )
    
    history = model.fit(
        X_train, y_train, 
        epochs=EPOCHS, 
        batch_size=BATCH_SIZE, 
        validation_split=0.1,      # Cắt 10% train làm bài kiểm tra
        callbacks=[early_stop], 
        verbose=0
    )
    
    # In ra số Epochs thực tế đã chạy
    actual_epochs = len(history.history['loss'])
    print(f"--> Đã dừng tại Epoch {actual_epochs}/{EPOCHS}. Thời gian: {time.time() - start_time:.2f}s")
    return model

# =============================================================================
# 4. CHƯƠNG TRÌNH CHÍNH
# =============================================================================
if __name__ == "__main__":
    # --- BƯỚC 1: Lấy dữ liệu đầy đủ ---
    data_values, dates = get_data_full_features(SYMBOL)
    if data_values is None: 
        print("Không đủ dữ liệu."); exit()

    # Chia Train/Test (80-20)
    train_size = int(len(data_values) * 0.8)
    data_train = data_values[:train_size]
    data_test = data_values[train_size:]
    dates_test = dates[train_size:]

    # Scale dữ liệu
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data_values)

    # Tạo X_train, y_train
    train_scaled = scaled_data[:train_size]
    X_train, y_train = prepare_data_multivariate(train_scaled, LOOK_BACK)

    # Chuẩn bị dữ liệu Test
    inputs = scaled_data[len(scaled_data) - len(data_test) - LOOK_BACK:]
    X_test = []
    for i in range(LOOK_BACK, len(inputs)):
        X_test.append(inputs[i-LOOK_BACK:i])
    X_test = np.array(X_test)

    results = {}
    
    # Helper inverse
    def inverse_price(pred_array):
        dummy = np.zeros((len(pred_array), 6))
        dummy[:, 0] = pred_array[:, 0]
        return scaler.inverse_transform(dummy)[:, 0]

    # --- BƯỚC 2: CHẠY MODEL ---
    
    # 1. RNN
    model_rnn = build_and_train_model('RNN', X_train, y_train)
    pred_rnn = model_rnn.predict(X_test)
    results['RNN'] = inverse_price(pred_rnn)

    # 2. LSTM
    model_lstm = build_and_train_model('LSTM', X_train, y_train)
    pred_lstm = model_lstm.predict(X_test)
    results['LSTM'] = inverse_price(pred_lstm)

    # 3. ARIMA
    print("\n[Training] ARIMA...")
    try:
        train_close = data_train[:, 0]
        model_arima = ARIMA(train_close, order=(5,1,0))
        model_fit = model_arima.fit()
        results['ARIMA'] = model_fit.forecast(steps=len(data_test))
    except: pass

    # --- BƯỚC 3: TÍNH TOÁN & VẼ (STYLE CŨ) ---
    print("\n--> Đang tính toán và vẽ biểu đồ...")
    
    y_real = data_test[:, 0] # Giá thực tế
    score_board = []

    # Tính sai số trước
    print("\n--- KẾT QUẢ SO SÁNH ---")
    for name, pred in results.items():
        min_len = min(len(y_real), len(pred))
        rmse = math.sqrt(mean_squared_error(y_real[:min_len], pred[:min_len]))
        mape = mean_absolute_percentage_error(y_real[:min_len], pred[:min_len]) * 100
        score_board.append(f"{name}: RMSE={rmse:,.0f}") # Chỉ hiện RMSE lên hình cho gọn
        print(f" > {name}: RMSE={rmse:,.0f} VNĐ | MAPE={mape:.2f}%")

    # Vẽ biểu đồ đơn giản
    plt.figure(figsize=(12, 6))
    
    # Vẽ giá thực tế (Màu đen)
    plt.plot(dates_test, y_real, label='Thực Tế', color='black', linewidth=2)
    
    # Vẽ các model
    colors = {'RNN': 'blue', 'LSTM': 'green', 'ARIMA': 'red'}
    styles = {'RNN': '--', 'LSTM': '-', 'ARIMA': ':'}

    for name, pred in results.items():
        plt.plot(dates_test, pred[:len(dates_test)], 
                 label=name, 
                 color=colors.get(name), 
                 linestyle=styles.get(name))

    plt.title(f'So sánh dự báo giá: {SYMBOL}')
    plt.xlabel('Thời gian')
    plt.ylabel('Giá (VNĐ)')
    plt.legend()
    plt.grid(True)
    
    # In điểm số vào góc biểu đồ
    plt.text(0.02, 0.95, '\n'.join(score_board), transform=plt.gca().transAxes,
             bbox=dict(facecolor='white', alpha=0.8), verticalalignment='top')
    
    plt.show()