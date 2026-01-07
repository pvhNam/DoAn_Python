import pandas as pd
import numpy as np
import joblib
import os
from tensorflow.keras.models import load_model
from models.database import get_db
from datetime import datetime, timedelta

# ==============================================================================
# PHẦN 1: CÁC HÀM TÍNH TOÁN CHỈ BÁO KỸ THUẬT (Dùng chung cho cả AI và Logic)
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
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower

# ==============================================================================
# PHẦN 2: LOGIC PHÂN TÍCH CƠ BẢN (Rule-Based từ Database)
# ==============================================================================

def get_fundamental_analysis(symbol):
    """
    Hàm này không dùng AI, mà truy vấn Database để lấy ROE, ROA, Lợi nhuận, Tiền gửi...
    để đánh giá sức khỏe doanh nghiệp.
    """
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # --- SỬA 1: Thêm 'customer_deposits' vào câu lệnh SELECT ---
        sql = """
            SELECT year, roe, roa, net_profit, revenue, pe, pb, customer_deposits
            FROM financial_data_coban 
            WHERE symbol = %s 
            ORDER BY year DESC LIMIT 2
        """
        cursor.execute(sql, (symbol,))
        rows = cursor.fetchall()
        cursor.close()
        
        if not rows:
            return "Chưa có dữ liệu báo cáo tài chính."

        latest = rows[0] # Năm mới nhất
        prev = rows[1] if len(rows) > 1 else None # Năm trước
        
        notes = []
        
        # 1. Đánh giá ROE (Vốn chủ sở hữu)
        roe = float(latest.get('roe') or 0)
        # Fix lỗi đơn vị: Nếu trong DB lưu 0.15 thì nhân 100, nếu lưu 15 thì giữ nguyên
        if roe < 1: roe = roe * 100 
        
        if roe > 15: notes.append(f"ROE rất tốt ({roe:.1f}%)")
        elif roe < 5: notes.append(f"⚠️ ROE thấp ({roe:.1f}%)")
        else: notes.append(f"ROE ổn định ({roe:.1f}%)")

        # --- SỬA 2: Thêm logic đánh giá ROA (Tài sản) ---
        roa = float(latest.get('roa') or 0)
        if roa < 1: roa = roa * 100
        
        if roa > 1.5: notes.append(f"ROA ấn tượng ({roa:.2f}%)") # Ngân hàng > 1.5% là ngon
        elif roa < 0.5: notes.append(f"⚠️ ROA thấp ({roa:.2f}%)")

        # 2. Đánh giá Tăng trưởng Lợi nhuận
        if prev:
            profit_now = float(latest.get('net_profit') or 0)
            profit_prev = float(prev.get('net_profit') or 0)
            
            if profit_prev != 0:
                growth = ((profit_now - profit_prev) / abs(profit_prev)) * 100
                if growth > 20: notes.append(f"Lợi nhuận tăng mạnh (+{growth:.1f}%)")
                elif growth < -20: notes.append(f"⚠️ Lợi nhuận giảm mạnh ({growth:.1f}%)")

            # --- SỬA 3: Thêm logic Tiền gửi khách hàng (Quan trọng với Bank) ---
            dep_now = float(latest.get('customer_deposits') or 0)
            dep_prev = float(prev.get('customer_deposits') or 0)
            
            if dep_now > 0 and dep_prev > 0:
                dep_growth = ((dep_now - dep_prev) / dep_prev) * 100
                if dep_growth > 15: 
                    notes.append(f"Tiền gửi tăng mạnh (+{dep_growth:.1f}%) → Nguồn vốn dồi dào")
                elif dep_growth < 0:
                    notes.append(f"Tiền gửi sụt giảm ({dep_growth:.1f}%)")

        # 3. Định giá P/E
        pe = float(latest.get('pe') or 0)
        if 0 < pe < 10: notes.append(f"Định giá rẻ (P/E={pe:.1f})")
        elif pe > 20: notes.append(f"Định giá cao (P/E={pe:.1f})")

        return " • ".join(notes) if notes else "Chỉ số cơ bản ở mức trung bình."

    except Exception as e:
        print(f"Lỗi Fundamental {symbol}: {e}")
        return ""

# ==============================================================================
# PHẦN 3: XỬ LÝ DỮ LIỆU CHO AI (Data Preparation)
# ==============================================================================

def prepare_data_for_ai(df):
    # Tính lại các chỉ báo y hệt lúc train để AI hiểu
    df['RSI'] = calculate_rsi(df['close'])
    df['MACD'], _ = calculate_macd(df['close']) # Lúc train mình chỉ dùng cột MACD line
    mid, upper, lower = calculate_bollinger_bands(df['close'])
    df['BB_Upper'] = upper
    df['BB_Lower'] = lower
    
    df.dropna(inplace=True)
    
    # 6 Cột Features bắt buộc (Phải khớp với file train_ai.py)
    features = ['close', 'volume', 'RSI', 'MACD', 'BB_Upper', 'BB_Lower']
    return df[features]

# ==============================================================================
# PHẦN 4: HÀM TỔNG HỢP (MAIN PREDICT FUNCTION)
# ==============================================================================

def predict_trend(symbol, days_ahead=14):
    symbol = symbol.upper()
    
    # --- BƯỚC 1: KIỂM TRA MODEL AI ---
    model_path = f'models_ai/{symbol}_lstm.keras'
    scaler_path = f'models_ai/{symbol}_scaler.pkl'
    
    if not os.path.exists(model_path):
        return [], "CHƯA HỌC", f"AI chưa có dữ liệu training cho mã {symbol}", 0

    try:
        # --- BƯỚC 2: LẤY DỮ LIỆU LỊCH SỬ ---
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT date, close, volume FROM stock_history WHERE symbol = '{symbol}' ORDER BY date ASC")
        rows = cursor.fetchall()
        cursor.close()
        
        if len(rows) < 100:
            return [], "THIẾU DATA", "Không đủ dữ liệu lịch sử", 0

        df = pd.DataFrame(rows)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        current_price = df['close'].iloc[-1]
        last_date_str = str(df['date'].iloc[-1])

        # --- BƯỚC 3: AI DỰ BÁO (Lớp Deep Learning) ---
        df_features = prepare_data_for_ai(df)
        
        if len(df_features) < 60:
             return [], "KHÔNG ĐỦ DATA", "Cần ít nhất 60 phiên liên tục", 0
             
        # Lấy 60 phiên gần nhất
        data_last_60 = df_features.values[-60:]
        
        # Load bộ não AI
        scaler = joblib.load(scaler_path)
        model = load_model(model_path)
        
        # Chuẩn hóa & Dự báo
        input_scaled = scaler.transform(data_last_60)
        X_input = np.array([input_scaled]) # Reshape (1, 60, 6)
        
        predicted_scaled = model.predict(X_input) # Kết quả 0-1
        
        # Đổi lại ra tiền Việt
        dummy = np.zeros((1, 6))
        dummy[0, 0] = predicted_scaled[0, 0]
        predicted_price = scaler.inverse_transform(dummy)[0, 0]
        
        # Tính % thay đổi
        pct_change = ((predicted_price - current_price) / current_price) * 100
        
        # --- BƯỚC 4: KẾT HỢP LOGIC KỸ THUẬT & CƠ BẢN (Lớp Rule-Based) ---
        
        reasons = []
        score = 50 # Điểm gốc
        
        # 4.1. Kết quả từ AI
        reasons.append(f"AI Neural Network dự báo giá mục tiêu: {predicted_price:,.0f} ({pct_change:+.2f}%)")
        
        if pct_change > 2:
            trend = "TĂNG MẠNH"
            score += 30
        elif pct_change > 0.5:
            trend = "TĂNG NHẸ"
            score += 15
        elif pct_change < -2:
            trend = "GIẢM MẠNH"
            score -= 30
        elif pct_change < -0.5:
            trend = "GIẢM NHẸ"
            score -= 15
        else:
            trend = "ĐI NGANG"

        # 4.2. Logic Kỹ thuật (Golden Cross)
        ma50 = df['close'].rolling(50).mean().iloc[-1]
        ma200 = df['close'].rolling(200).mean().iloc[-1]
        
        if ma50 > ma200:
            reasons.append("Golden Cross (MA50 > MA200) → Xu hướng dài hạn TĂNG")
            score += 10
        elif ma50 < ma200:
            reasons.append("Death Cross (MA50 < MA200) → Xu hướng dài hạn GIẢM")
            score -= 10
            
        # 4.3. Logic Kỹ thuật (RSI)
        last_rsi = df_features['RSI'].iloc[-1]
        if last_rsi > 70: 
            reasons.append("Cảnh báo: RSI đang vùng Quá mua (>70)")
            score -= 5 # Trừ bớt điểm vì rủi ro điều chỉnh
        elif last_rsi < 30: 
            reasons.append("Cơ hội: RSI đang vùng Quá bán (<30)")
            score += 5

        # 4.4. Logic Cơ bản (Fundamental - Gọi hàm ở phần 2)
        fund_text = get_fundamental_analysis(symbol)
        if fund_text:
            reasons.append(f"[Cơ bản] {fund_text}")
            # Cộng điểm thêm nếu cơ bản tốt
            if "tốt" in fund_text or "mạnh" in fund_text: score += 10
            if "thấp" in fund_text or "giảm" in fund_text: score -= 10

        # Chốt điểm số (0 - 100)
        score = int(max(0, min(100, score)))
        final_reason = "|||".join(reasons) # Xuống dòng cho đẹp trên web

        # Dữ liệu vẽ biểu đồ dự báo
        last_date_obj = df['date'].iloc[-1] # Lấy object date cuối cùng
        
        # Nếu database trả về string thì convert, nếu là date thì dùng luôn
        if isinstance(last_date_obj, str):
            last_date_obj = datetime.strptime(last_date_obj, '%Y-%m-%d').date()
            
        next_date_obj = last_date_obj + timedelta(days=1)
        next_date_str = next_date_obj.strftime('%Y-%m-%d') # Ra dạng '2025-12-31'
        
        chart_data = [
            {"time": str(last_date_obj), "value": current_price},
            {"time": next_date_str, "value": predicted_price} # Đã sửa thành ngày chuẩn
        ]
        
        print(f"✅ AI {symbol}: {current_price:,.0f} -> {predicted_price:,.0f} | Score: {score}")
        
        return chart_data, trend, final_reason, score

    except Exception as e:
        print(f"❌ Lỗi Analysis {symbol}: {e}")
        return [], "LỖI", "Không thể phân tích lúc này", 0