import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta
from models.database import get_db

# HÀM TÍNH RSI
def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    
    # Tránh chia cho 0
    rs = gain / loss.replace(0, 0.001)
    return 100 - (100 / (1 + rs))

# HÀM LẤY DỮ LIỆU CƠ BẢN TỪ DB
def get_fundamental_analysis(symbol):
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        # Lấy dữ liệu 2 năm gần nhất
        cursor.execute("""
            SELECT year, profit, assets FROM financial_data 
            WHERE symbol = %s ORDER BY year DESC LIMIT 2
        """, (symbol,))
        rows = cursor.fetchall()
        cursor.close()
        
        if not rows:
            return "" # Không có dữ liệu thì trả về rỗng

        # Phân tích tăng trưởng
        current = rows[0]
        report_text = []
        
        # Format số tiền (Tỷ đồng)
        profit_bil = current['profit']
        assets_bil = current['assets']
        
        report_text.append(f"Lợi nhuận năm {current['year']}: {profit_bil:,.0f} tỷ.")

        # So sánh với năm trước 
        if len(rows) > 1:
            prev = rows[1]
            if prev['profit'] and prev['profit'] != 0:
                growth = ((current['profit'] - prev['profit']) / abs(prev['profit'])) * 100
                if growth > 20:
                    report_text.append(f"Tăng trưởng mạnh mẽ (+{growth:.1f}%) so với năm trước. Tín hiệu tốt về dài hạn.")
                elif growth > 0:
                    report_text.append(f"Tăng trưởng ổn định (+{growth:.1f}%).")
                else:
                    report_text.append(f"Lợi nhuận suy giảm ({growth:.1f}%) so với cùng kỳ. Cần thận trọng.")
        
        return " ".join(report_text)

    except Exception as e:
        print(f"Lỗi Fundamental: {e}")
        return ""

# HÀM DỰ ĐOÁN CHÍNH
def predict_trend(symbol, days_ahead=14):
    try:
        #  LẤY DỮ LIỆU KỸ THUẬT
        ticker = yf.Ticker(f"{symbol}.VN")
        df = ticker.history(period="1y") # Lấy 1 năm
        
        if len(df) < 50:
            return [], "Không đủ dữ liệu", "Chưa có nhận định"

        # Tính chỉ báo
        df['RSI'] = calculate_rsi(df['Close'])
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        current_price = df['Close'].iloc[-1]
        current_rsi = df['RSI'].iloc[-1]
        current_ma20 = df['MA20'].iloc[-1]

        # CHẠY MÔ HÌNH AI (LINEAR REGRESSION) ---
        df_train = df.tail(60).reset_index() # Train 60 ngày
        df_train['Date_Ordinal'] = df_train['Date'].map(pd.Timestamp.toordinal)
        
        X = df_train[['Date_Ordinal']].values
        y = df_train['Close'].values

        model = LinearRegression()
        model.fit(X, y)

        # Dự báo tương lai
        last_date = df_train['Date'].iloc[-1]
        future_data = []
        future_dates_ordinal = []
        display_dates = []

        for i in range(1, days_ahead + 1):
            next_date = last_date + timedelta(days=i)
            if next_date.weekday() < 5: # Bỏ T7, CN
                future_dates_ordinal.append([next_date.toordinal()])
                display_dates.append(next_date)

        if not future_dates_ordinal:
             return [], "Lỗi ngày", "Không thể dự đoán"

        predictions = model.predict(future_dates_ordinal)

        # Đóng gói dữ liệu vẽ chart
        last_real_point = {"time": last_date.strftime('%Y-%m-%d'), "value": float(y[-1])}
        future_data.append(last_real_point)

        for i, pred in enumerate(predictions):
            future_data.append({
                "time": display_dates[i].strftime('%Y-%m-%d'),
                "value": float(pred)
            })

        # TỔNG HỢP NHẬN ĐỊNH
        reasons = []
        
        # Phân tích Xu hướng (AI)
        start_p = y[-1]
        end_p = predictions[-1]
        pct_change = ((end_p - start_p) / start_p) * 100
        
        if pct_change > 3.0: trend = "TĂNG MẠNH "
        elif pct_change > 0.5: trend = "TĂNG NHẸ "
        elif pct_change > -0.5: trend = "ĐI NGANG "
        elif pct_change > -3.0: trend = "GIẢM NHẸ "
        else: trend = "GIẢM MẠNH "

        # Phân tích Kỹ thuật (RSI & MA)
        if current_rsi > 70: reasons.append("RSI báo Quá Mua (Rủi ro điều chỉnh).")
        elif current_rsi < 30: reasons.append("RSI báo Quá Bán (Cơ hội bắt đáy).")
        
        if current_price > current_ma20: reasons.append("Giá trên MA20 (Xu hướng ngắn hạn Tốt).")
        else: reasons.append("Giá dưới MA20 (Xu hướng ngắn hạn Yếu).")

        #  Phân tích Cơ bản (Lấy từ Database)
        fund_text = get_fundamental_analysis(symbol)
        if fund_text:
            reasons.append(f"| [Cơ bản] {fund_text}")

        reasons.append(f"| [AI] Dự báo {trend.split()[0]} {abs(pct_change):.1f}% trong 2 tuần tới.")

        final_reason = " ".join(reasons)
        
        return future_data, trend, final_reason

    except Exception as e:
        print(f"AI Error: {e}")
        return [], "Lỗi hệ thống", str(e)