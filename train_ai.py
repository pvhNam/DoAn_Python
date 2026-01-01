import numpy as np
import pandas as pd
import mysql.connector
import os
import joblib  # Dùng để lưu file Scaler (bộ chuẩn hóa)
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

# --- CẤU HÌNH ---
# 1. Cấu hình Database (Lấy từ database.py của bạn)
DB_CONFIG = {
    'user': 'root',
    'password': '123456',
    'host': '127.0.0.1',
    'database': 'python',
    'raise_on_warnings': True
}

# 2. Cấu hình Model
LOOK_BACK = 60  # Số ngày quá khứ dùng để dự đoán ngày tiếp theo (Window size)
EPOCHS = 20     # Số vòng lặp huấn luyện (càng cao càng lâu nhưng có thể chính xác hơn)
BATCH_SIZE = 32 # Số lượng mẫu dữ liệu đưa vào học mỗi lần
MODEL_DIR = 'models/ai_checkpoints' # Thư mục lưu file model

# Tạo thư mục lưu model nếu chưa có
if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR)

def get_stock_data(symbol):
    """Kết nối DB và lấy lịch sử giá đóng cửa (Close)"""
    conn = None
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        query = f"""
            SELECT date, close 
            FROM stock_history 
            WHERE symbol = '{symbol}' 
            ORDER BY date ASC
        """
        df = pd.read_sql(query, conn)
        return df
    except Exception as e:
        print(f"Lỗi lấy dữ liệu {symbol}: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()

def train_model_for_symbol(symbol):
    print(f"\n>>> BẮT ĐẦU TRAINING CHO MÃ: {symbol}")
    
    # 1. Lấy dữ liệu
    df = get_stock_data(symbol)
    if df is None or len(df) < LOOK_BACK + 10:
        print(f"❌ Không đủ dữ liệu để train (Cần tối thiểu {LOOK_BACK + 10} ngày)")
        return

    data = df.filter(['close']).values # Chỉ lấy cột giá đóng cửa

    # 2. Chuẩn hóa dữ liệu (Scaling) về khoảng 0 - 1
    # LSTM rất nhạy cảm với số lớn, nên bắt buộc phải ép về 0-1
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)

    # 3. Tạo tập dữ liệu Train (X: 60 ngày trước, Y: Ngày hiện tại)
    x_train = []
    y_train = []

    for i in range(LOOK_BACK, len(scaled_data)):
        x_train.append(scaled_data[i-LOOK_BACK:i, 0])
        y_train.append(scaled_data[i, 0])

    # Chuyển sang numpy array để đưa vào TensorFlow
    x_train, y_train = np.array(x_train), np.array(y_train)

    # Reshape dữ liệu thành 3D [Samples, Time Steps, Features] theo yêu cầu LSTM
    x_train = np.reshape(x_train, (x_train.shape[0], x_train.shape[1], 1))

    # 4. Xây dựng kiến trúc mạng LSTM
    print(f"🏗️  Đang xây dựng model LSTM...")
    model = Sequential()
    
    # Lớp LSTM 1: 50 nơ-ron, trả về sequence để lớp sau dùng tiếp
    model.add(LSTM(units=50, return_sequences=True, input_shape=(x_train.shape[1], 1)))
    model.add(Dropout(0.2)) # Chống học vẹt (Overfitting)

    # Lớp LSTM 2: 50 nơ-ron, không trả sequence (lớp cuối cùng của LSTM)
    model.add(LSTM(units=50, return_sequences=False))
    model.add(Dropout(0.2))

    # Lớp Dense: Trả về 1 giá trị duy nhất (Giá dự đoán)
    model.add(Dense(units=25))
    model.add(Dense(units=1))

    # Compile model
    model.compile(optimizer='adam', loss='mean_squared_error')

    # 5. Huấn luyện (Training)
    print(f"🚀 Đang train (Epochs: {EPOCHS})... Vui lòng đợi...")
    model.fit(x_train, y_train, batch_size=BATCH_SIZE, epochs=EPOCHS, verbose=1)

    # 6. Lưu Model và Scaler
    # Lưu Model (.h5)
    model_path = os.path.join(MODEL_DIR, f"{symbol}_lstm.h5")
    model.save(model_path)
    
    # Lưu Scaler (.pkl) -> Rất quan trọng! 
    # Nếu không lưu cái này, lúc dự đoán sẽ không biết quy đổi giá trị về lại tiền VNĐ.
    scaler_path = os.path.join(MODEL_DIR, f"{symbol}_scaler.pkl")
    joblib.dump(scaler, scaler_path)

    print(f"✅ Đã hoàn tất train {symbol}!")
    print(f"   - Model lưu tại: {model_path}")
    print(f"   - Scaler lưu tại: {scaler_path}")

# --- MAIN PROGRAM ---
if __name__ == "__main__":
    # Danh sách các mã cổ phiếu bạn muốn train AI
    # Lưu ý: Trong DB phải có dữ liệu lịch sử của các mã này (chạy file 1ydata.py trước)
    target_symbols = ["ACB", "BID", "BVH", "CTG", "FPT", "GAS", "HPG", "MBB", "MSN", "MWG", 
               "NVL", "PDR", "PLX", "PNJ", "POW", "SAB", "SSI", "STB", "TCB", "TPB", 
               "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE","DPM"] 

    print("=== HỆ THỐNG TRAINING AI STOCK ===")
    for s in target_symbols:
        train_model_for_symbol(s)
    
    print("\n🎉 TẤT CẢ ĐÃ HOÀN TẤT!")