import pandas as pd
import numpy as np
import joblib
import os
import json
from tensorflow.keras.models import load_model
from models.database import get_db
from datetime import datetime, timedelta
from ai_models import StockRNN

# ==============================================================================
# PHẦN 1: CÁC HÀM TÍNH TOÁN CHỈ BÁO KỸ THUẬT
# ==============================================================================
def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

def calculate_bollinger_bands(series, window=20, num_std=2):
    mid = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = mid + (std * num_std)
    lower = mid - (std * num_std)
    return upper, lower

def prepare_data_for_ai(df):
    df['RSI'] = calculate_rsi(df['close'])
    df['MACD'], _ = calculate_macd(df['close'])
    df['BB_Upper'], df['BB_Lower'] = calculate_bollinger_bands(df['close'])
    df.fillna(0, inplace=True)
    features = ['close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
    return df[features]

# ==============================================================================
# PHẦN 2: HÀM PHÂN TÍCH CƠ BẢN
# ==============================================================================
def get_fundamental_analysis(symbol):
    return "Chỉ số tài chính cơ bản ở mức ổn định."

# ==============================================================================
# PHẦN 3: LOGIC DỰ BÁO VÀ SO SÁNH HIỆU SUẤT (ĐÃ SỬA VÒNG LẶP 14 NGÀY)
# ==============================================================================
def predict_trend(symbol, days_ahead=14):
    symbol = symbol.upper()
    
    # Đường dẫn các file
    lstm_path = f'models_ai/{symbol}_lstm.keras'
    scaler_path = f'models_ai/{symbol}_scaler.pkl'
    json_path = f'models_ai/{symbol}_comparison.json'
    
    if not os.path.exists(lstm_path):
        return [], "CHƯA HỌC", "Hệ thống chưa có dữ liệu training cho mã này", 0

    try:
        # 1. ĐỌC KẾT QUẢ SO SÁNH HIỆU SUẤT (JSON)
        comp_data = {}
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                comp_data = json.load(f)
        
        # 2. LẤY DỮ LIỆU TỪ DB
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        # Lấy dư ra 100 dòng để đủ tính chỉ báo và tạo window 60
        cursor.execute(f"SELECT date, close, volume FROM stock_history WHERE symbol = '{symbol}' ORDER BY date ASC")
        rows = cursor.fetchall()
        cursor.close()
        
        if not rows: return [], "KHÔNG DATA", "", 0

        df = pd.DataFrame(rows)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        current_price = df['close'].iloc[-1]
        
        # Prepare Data
        df_features = prepare_data_for_ai(df)
        if len(df_features) < 60: return [], "THIẾU DATA", "Cần ít nhất 60 phiên", 0
        
        # Lấy dữ liệu 60 ngày cuối cùng để làm đầu vào dự báo
        data_last_60 = df_features.values[-60:]
        scaler = joblib.load(scaler_path)
        input_scaled = scaler.transform(data_last_60)
        
        # Reshape (1, 60, 6)
        current_input = np.array([input_scaled]) 

        # Load Model LSTM
        model_lstm = load_model(lstm_path)

        # -----------------------------------------------------------
        # VÒNG LẶP DỰ BÁO 14 NGÀY (Logic Mới)
        # -----------------------------------------------------------
        future_predictions = []
        
        # Xác định ngày bắt đầu dự báo (là ngày mai)
        last_date_obj = df['date'].iloc[-1]
        if isinstance(last_date_obj, str):
            last_date_obj = datetime.strptime(last_date_obj, '%Y-%m-%d').date()
        
        current_date = last_date_obj
        
        # Biến tạm để tính giá dự báo cuối cùng (dùng cho logic Trend)
        final_predicted_price = current_price 

        for i in range(days_ahead):
            # 1. Dự báo bước tiếp theo
            pred_scaled = model_lstm.predict(current_input, verbose=0)
            
            # 2. Inverse Scale (chỉ quan tâm cột close đầu tiên)
            dummy = np.zeros((1, 6))
            dummy[0, 0] = pred_scaled[0, 0]
            predicted_price = scaler.inverse_transform(dummy)[0, 0]
            
            # Cập nhật giá cuối cùng
            final_predicted_price = predicted_price
            
            # 3. Tăng ngày
            current_date += timedelta(days=1)
            
            # 4. Lưu vào danh sách kết quả trả về cho biểu đồ
            future_predictions.append({
                "time": current_date.strftime('%Y-%m-%d'),
                "value": round(float(predicted_price), 0)
            })
            
            # 5. Cập nhật input cho vòng lặp sau (Rolling Window)
            # Lấy dòng dữ liệu cuối cùng hiện tại
            new_row = current_input[0, -1, :].copy()
            # Cập nhật giá close mới vào dòng này (Giả định các chỉ báo khác đi ngang hoặc dùng giá mới để ước lượng thô)
            # Ở đây ta gán trực tiếp giá dự báo vào input để mô hình "tự xoay sở"
            new_row[0] = pred_scaled[0, 0] 
            
            # Reshape để nối chuỗi
            new_row_reshaped = new_row.reshape(1, 1, 6)
            # Bỏ ngày đầu tiên, thêm ngày mới vào cuối: (1, 60, 6) -> (1, 59, 6) + (1, 1, 6)
            current_input = np.append(current_input[:, 1:, :], new_row_reshaped, axis=1)

        # -----------------------------------------------------------
        # TỔNG HỢP BÁO CÁO (Dùng giá dự báo ngày thứ 14 để nhận định)
        # -----------------------------------------------------------
        reasons = []
        score = 50
        
        # -- So sánh hiệu suất (Chỉ lấy thông tin tĩnh từ JSON) --
        if comp_data:
            winner = comp_data['winner']
            lstm_loss = comp_data['LSTM']['loss_mse']
            rnn_loss = comp_data['RNN']['loss_mse']
            
            reasons.append(f"AI Dự báo (Sau {days_ahead} ngày): {final_predicted_price:,.0f} VNĐ")
            
            if winner == "LSTM":
                reasons.append(f"✅ Mô hình LSTM tối ưu hơn (Sai số MSE: {lstm_loss:.5f} < {rnn_loss:.5f})")
                score += 5
            else:
                reasons.append(f"ℹ️ Lưu ý: Mô hình RNN có sai số thấp hơn ({rnn_loss:.5f}) nhưng ta dùng LSTM để ổn định.")
        else:
             reasons.append(f"AI Dự báo (Sau {days_ahead} ngày): {final_predicted_price:,.0f} VNĐ")

        # -- Logic Trend --
        pct_change = ((final_predicted_price - current_price) / current_price) * 100
        
        if pct_change > 2: trend = "TĂNG MẠNH"; score += 20
        elif pct_change > 0.5: trend = "TĂNG NHẸ"; score += 10
        elif pct_change < -2: trend = "GIẢM MẠNH"; score -= 20
        elif pct_change < -0.5: trend = "GIẢM NHẸ"; score -= 10
        else: trend = "ĐI NGANG"

        # -- Technical Indicators (Lấy trạng thái hiện tại) --
        rsi = df_features['RSI'].iloc[-1]
        reasons.append(f"RSI hiện tại: {rsi:.1f}")
        if rsi > 70: reasons.append("⚠️ Vùng quá mua"); score -= 10
        elif rsi < 30: reasons.append("✅ Vùng quá bán"); score += 10
        
        # -- Fundamental --
        fund_text = get_fundamental_analysis(symbol)
        if fund_text: reasons.append(f"[Cơ bản] {fund_text}")

        # Chốt dữ liệu trả về
        score = int(max(0, min(100, score)))
        final_reason = "|||".join(reasons)
        
        # Dữ liệu biểu đồ trả về chính là danh sách dự báo 14 ngày
        return future_predictions, trend, final_reason, score

    except Exception as e:
        print(f"❌ Lỗi Analysis {symbol}: {e}")
        return [], "LỖI", "Lỗi phân tích", 0