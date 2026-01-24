import mysql.connector
import pandas as pd
import numpy as np
import joblib
import matplotlib.pyplot as plt
import warnings
from tensorflow.keras.models import load_model
from ai_models import StockRNN
from datetime import datetime

# --- THƯ VIỆN ĐÁNH GIÁ & ARIMA ---
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from statsmodels.tsa.arima.model import ARIMA

# Tắt cảnh báo của ARIMA để đỡ rối mắt
warnings.filterwarnings("ignore")

DB_CONFIG = {
    'user': 'root', 'password': '123456',
    'host': 'localhost', 'database': 'python'
}

# --- CẤU HÌNH ---
SPLIT_DATE = '2024-10-01'
TEST_DAYS = 30  # Chạy thử 30 ngày
SYMBOL = 'MBB' 

# Hàm chỉ báo kỹ thuật
def add_technical_indicators(df):
    # Lưu ý: Dữ liệu vào đã được đổi tên thành adjusted_close ở bước query
    delta = df['adjusted_close'].diff()
    
    # RSI chuẩn quốc tế dùng window=14 (code cũ bạn để 30 hơi dài, mình chỉnh về 14 cho nhạy)
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
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

# Hàm tính toán chỉ số đánh giá
def calculate_metrics(y_true, y_pred, model_name):
    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    
    # Xử lý trường hợp chia cho 0
    with np.errstate(divide='ignore', invalid='ignore'):
        mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100
        
    r2 = r2_score(y_true, y_pred)
    
    return {
        "Model": model_name,
        "MAE (VNĐ)": round(mae, 0),
        "RMSE (VNĐ)": round(rmse, 0),
        "MAPE (%)": round(mape, 2),
        "R2 Score": round(r2, 4)
    }

def run_simulation():
    print(f"📥 Đang tải dữ liệu Adjusted Close và Model cho {SYMBOL}...")
    
    # 1. Load LSTM & RNN
    try:
        model_lstm = load_model(f'models_backtest/{SYMBOL}_lstm.keras')
        
        rnn_agent = StockRNN(SYMBOL)
        rnn_agent.model_path = f'models_backtest/{SYMBOL}_rnn.keras'
        rnn_agent.load_model()
        model_rnn = rnn_agent.model
        
        scaler = joblib.load(f'models_backtest/{SYMBOL}_scaler.pkl')
    except Exception as e:
        print(f"❌ Lỗi load model: {e}")
        print("👉 Hãy chạy file train_backtest.py trước!")
        return

    # 2. Lấy dữ liệu
    conn = mysql.connector.connect(**DB_CONFIG)
    # [QUAN TRỌNG]: Dùng 'AS adjusted_close' để khớp tên biến mà không cần sửa DB
    query = f"SELECT date, adjusted_close, volume FROM stock_history WHERE symbol = '{SYMBOL}' ORDER BY date ASC"
    df = pd.read_sql(query, conn)
    conn.close()
    
    df = add_technical_indicators(df)
    features = ['adjusted_close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
    
    split_date_obj = datetime.strptime(SPLIT_DATE, '%Y-%m-%d').date()
    mask = df['date'] >= split_date_obj
    
    if not mask.any():
        print(f"❌ Không có dữ liệu sau ngày {SPLIT_DATE}!")
        return
        
    start_idx = df[mask].index[0]
    
    # Danh sách lưu kết quả
    dates, actuals = [], []
    lstm_preds, rnn_preds, arima_preds = [], [], []
    
    print(f"📊 Bắt đầu chạy so sánh 3 mô hình ({TEST_DAYS} ngày)...")
    
    for i in range(TEST_DAYS):
        current_idx = start_idx + i
        if current_idx >= len(df): break
        
        # --- A. DỰ BÁO BẰNG AI (LSTM & RNN) ---
        input_data_raw = df[features].iloc[current_idx-60 : current_idx].values
        if len(input_data_raw) < 60: continue
        
        input_scaled = scaler.transform(input_data_raw)
        X_input = np.array([input_scaled]) 
        
        # LSTM
        pred_lstm_scaled = model_lstm.predict(X_input, verbose=0)
        dummy_lstm = np.zeros((1, 6))
        dummy_lstm[0, 0] = pred_lstm_scaled[0, 0]
        pred_lstm = scaler.inverse_transform(dummy_lstm)[0, 0]
        
        # RNN
        pred_rnn_scaled = model_rnn.predict(X_input, verbose=0)
        dummy_rnn = np.zeros((1, 6))
        dummy_rnn[0, 0] = pred_rnn_scaled[0, 0]
        pred_rnn = scaler.inverse_transform(dummy_rnn)[0, 0]
        
        # --- B. DỰ BÁO BẰNG ARIMA (Thống kê) ---
        history_prices = df['adjusted_close'].iloc[:current_idx].values
        
        try:
            # Order (5,1,0): AutoRegressive
            arima_model = ARIMA(history_prices, order=(5,1,0)) 
            arima_fit = arima_model.fit()
            pred_arima = arima_fit.forecast(steps=1)[0]
        except:
            pred_arima = history_prices[-1] 
            
        # --- C. LƯU KẾT QUẢ ---
        actual_price = df['adjusted_close'].iloc[current_idx]
        actual_date = df['date'].iloc[current_idx]
        
        dates.append(actual_date)
        actuals.append(actual_price)
        lstm_preds.append(pred_lstm)
        rnn_preds.append(pred_rnn)
        arima_preds.append(pred_arima)
        
        print(f"🗓 {actual_date} | Adj Close: {actual_price:,.0f} | LSTM: {pred_lstm:,.0f} | RNN: {pred_rnn:,.0f} | ARIMA: {pred_arima:,.0f}")

    # --- TÍNH TOÁN & HIỂN THỊ ---
    print("\n" + "="*70)
    print("📋 BẢNG SO SÁNH HIỆU SUẤT (DỰA TRÊN GIÁ ĐIỀU CHỈNH)")
    print("="*70)
    
    m_lstm = calculate_metrics(actuals, lstm_preds, "LSTM (Deep Learning)")
    m_rnn = calculate_metrics(actuals, rnn_preds, "RNN (Deep Learning)")
    m_arima = calculate_metrics(actuals, arima_preds, "ARIMA (Statistical)")
    
    results_df = pd.DataFrame([m_lstm, m_rnn, m_arima])
    print(results_df.to_string(index=False))
    print("="*70)
    
    # Tìm người chiến thắng
    best_mape = min(m_lstm['MAPE (%)'], m_rnn['MAPE (%)'], m_arima['MAPE (%)'])
    if best_mape == m_lstm['MAPE (%)']: winner = "LSTM"
    elif best_mape == m_rnn['MAPE (%)']: winner = "RNN"
    else: winner = "ARIMA"

    print(f"🏆 KẾT LUẬN: Mô hình {winner} dự báo chính xác nhất (MAPE thấp nhất).")
    print("="*70 + "\n")

    # Vẽ biểu đồ
    # Chỉnh lại kích thước 16x8 cho vừa vặn slide powerpoint, 30 hơi dài
    plt.figure(figsize=(16, 8)) 
    plt.plot(dates, actuals, label='Adjusted Close (Giá điều chỉnh)', color='black', linewidth=2.5)
    plt.plot(dates, lstm_preds, label=f'LSTM (MAPE={m_lstm["MAPE (%)"]}%)', color='green', linestyle='--')
    plt.plot(dates, rnn_preds, label=f'RNN (MAPE={m_rnn["MAPE (%)"]}%)', color='red', linestyle='--')
    plt.plot(dates, arima_preds, label=f'ARIMA (MAPE={m_arima["MAPE (%)"]}%)', color='blue', linestyle=':', linewidth=2)
    
    plt.title(f'BACKTEST: SO SÁNH LSTM vs RNN vs ARIMA ({SYMBOL})', fontsize=16, fontweight='bold')
    plt.xlabel('Thời gian')
    plt.ylabel('Giá điều chỉnh (VNĐ)')
    plt.legend(fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    run_simulation()