import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta

def calculate_rsi(data, window=14):
    """ Hàm tính chỉ báo RSI """
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def predict_trend(symbol, days_ahead=14):
    """
    Dự đoán giá và đưa ra lý do phân tích (Kỹ thuật & Xu hướng)
    """
    try:
        # 1. Lấy dữ liệu
        ticker = yf.Ticker(f"{symbol}.VN")
        # Lấy 1 năm để tính MA và RSI cho chuẩn
        df = ticker.history(period="1y") 
        
        if len(df) < 50:
            return [], "Không đủ dữ liệu phân tích", "Chưa có nhận định"

        # 2. Tính toán chỉ báo kỹ thuật (Technical Indicators)
        # RSI (Sức mạnh tương đối)
        df['RSI'] = calculate_rsi(df['Close'])
        # MA20 (Trung bình 20 phiên - Xu hướng ngắn hạn)
        df['MA20'] = df['Close'].rolling(window=20).mean()
        # MA50 (Trung bình 50 phiên - Xu hướng trung hạn)
        df['MA50'] = df['Close'].rolling(window=50).mean()

        # Lấy giá trị hiện tại (Phiên mới nhất)
        current_price = df['Close'].iloc[-1]
        current_rsi = df['RSI'].iloc[-1]
        current_ma20 = df['MA20'].iloc[-1]
        vol_avg = df['Volume'].rolling(window=20).mean().iloc[-1]
        current_vol = df['Volume'].iloc[-1]

        # 3. Chạy AI Linear Regression (Hồi quy tuyến tính)
        df_train = df.tail(60).reset_index() # Chỉ train 60 ngày gần nhất cho nhạy
        df_train['Date_Ordinal'] = df_train['Date'].map(pd.Timestamp.toordinal)
        
        X = df_train[['Date_Ordinal']].values
        y = df_train['Close'].values

        model = LinearRegression()
        model.fit(X, y)

        # 4. Dự đoán tương lai
        last_date = df_train['Date'].iloc[-1]
        future_data = []
        future_dates_ordinal = []
        display_dates = []

        for i in range(1, days_ahead + 1):
            next_date = last_date + timedelta(days=i)
            if next_date.weekday() < 5: 
                future_dates_ordinal.append([next_date.toordinal()])
                display_dates.append(next_date)

        if not future_dates_ordinal:
            return [], "Lỗi ngày", "Không thể dự đoán"

        predictions = model.predict(future_dates_ordinal)

        # Đóng gói dữ liệu vẽ biểu đồ
        last_real_point = {
            "time": last_date.strftime('%Y-%m-%d'),
            "value": float(y[-1])
        }
        future_data.append(last_real_point)

        for i, pred in enumerate(predictions):
            future_data.append({
                "time": display_dates[i].strftime('%Y-%m-%d'),
                "value": float(pred)
            })

        # ======================================================
        # 5. PHÂN TÍCH LOGIC (FIX LỖI NHẬN ĐỊNH SAI)
        # ======================================================
        
        # Tính % tăng trưởng dự báo: (Giá cuối - Giá đầu) / Giá đầu * 100
        start_p = y[-1]
        end_p = predictions[-1]
        pct_change = ((end_p - start_p) / start_p) * 100
        
        # Logic dán nhãn xu hướng dựa trên % (Chuẩn xác hơn Slope)
        if pct_change > 3.0: trend = "TĂNG MẠNH 🚀"
        elif pct_change > 0.5: trend = "TĂNG NHẸ 📈"
        elif pct_change > -0.5: trend = "ĐI NGANG ➖"
        elif pct_change > -3.0: trend = "GIẢM NHẸ 📉"
        else: trend = "GIẢM MẠNH 🩸"

        # ======================================================
        # 6. SINH LÝ DO (REASON) DỰA TRÊN KỸ THUẬT
        # ======================================================
        reasons = []

        # Phân tích RSI (Quá mua/Quá bán)
        if current_rsi > 70:
            reasons.append("RSI báo vùng Quá Mua (Overbought), rủi ro điều chỉnh cao.")
        elif current_rsi < 30:
            reasons.append("RSI báo vùng Quá Bán (Oversold), xuất hiện lực cầu bắt đáy kỹ thuật.")
        else:
            reasons.append(f"RSI ở mức trung tính ({int(current_rsi)}), xu hướng ổn định.")

        # Phân tích MA (Xu hướng dòng tiền)
        if current_price > current_ma20:
            reasons.append("Giá nằm trên MA20, xu hướng ngắn hạn tích cực.")
        else:
            reasons.append("Giá gãy MA20, áp lực bán ngắn hạn đang mạnh.")

        # Phân tích Volume (Dòng tiền)
        if current_vol > vol_avg * 1.5:
            if current_price > df['Close'].iloc[-2]:
                reasons.append("Thanh khoản đột biến: Dòng tiền lớn (Cá mập) đang nhập cuộc.")
            else:
                reasons.append("Thanh khoản đột biến chiều giảm: Áp lực xả hàng mạnh (Panic Sell).")

        # Kết hợp AI dự báo
        if pct_change > 0:
            reasons.append(f"Mô hình AI dự báo đà tăng trưởng {pct_change:.1f}% trong {days_ahead} ngày tới.")
        else:
            reasons.append(f"Mô hình AI cảnh báo rủi ro giảm {pct_change:.1f}% trong {days_ahead} ngày tới.")

        # Gộp thành 1 đoạn văn
        final_reason = " | ".join(reasons)
        
        return future_data, trend, final_reason

    except Exception as e:
        print(f"AI Error: {e}")
        return [], "Lỗi hệ thống", str(e)