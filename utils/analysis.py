import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from models.database import get_db

# ================== CÁC CHỈ BÁO KỸ THUẬT ==================

def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=window).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def calculate_bollinger_bands(series, window=20, num_std=2):
    mid = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower

# ================== PHÂN TÍCH CƠ BẢN TỪ DB ==================

def get_fundamental_analysis(symbol):
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Câu lệnh SQL của bạn (Đã đúng)
        cursor.execute("""
            SELECT year, total_assets, revenue, net_profit, roe, roa, customer_deposits
            FROM financial_data_coban 
            WHERE symbol = %s 
            ORDER BY year DESC LIMIT 3
        """, (symbol,))
        
        rows = cursor.fetchall()
        cursor.close()
        # LƯU Ý: KHÔNG dùng conn.close() ở đây nếu dùng chung kết nối trong Flask
        
        # Nếu không đủ dữ liệu
        if len(rows) < 2:
            return "Chưa đủ dữ liệu tài chính để phân tích."

        current = rows[0]
        prev = rows[1]
        report = []

        # --- HÀM HỖ TRỢ LẤY DỮ LIỆU AN TOÀN (Chống lỗi NULL) ---
        def get_safe_float(row, key):
            val = row.get(key)
            if val is None: 
                return 0.0
            return float(val)

        # 1. PHÂN TÍCH LỢI NHUẬN
        cur_profit = get_safe_float(current, 'net_profit')
        prev_profit = get_safe_float(prev, 'net_profit')

        if prev_profit != 0:
            profit_growth = (cur_profit - prev_profit) / abs(prev_profit) * 100
            if profit_growth > 20:
                report.append(f"Lợi nhuận tăng mạnh (+{profit_growth:.1f}%) – Tín hiệu rất tốt.")
            elif profit_growth > 0:
                report.append(f"Lợi nhuận tăng nhẹ (+{profit_growth:.1f}%).")
            elif profit_growth > -20:
                report.append(f"Lợi nhuận giảm nhẹ ({profit_growth:.1f}%).")
            else:
                report.append(f"⚠️ Lợi nhuận giảm mạnh ({profit_growth:.1f}%) – Rủi ro cao.")
        else:
            report.append("Không có dữ liệu lợi nhuận để so sánh.")

        # 2. TIỀN GỬI KHÁCH HÀNG
        cur_deposit = get_safe_float(current, 'customer_deposits')
        prev_deposit = get_safe_float(prev, 'customer_deposits')

        if cur_deposit > 0 and prev_deposit > 0:
            dep_growth = (cur_deposit - prev_deposit) / prev_deposit * 100
            if dep_growth > 10:
                report.append(f"Tiền gửi tăng mạnh (+{dep_growth:.1f}%) – Nguồn vốn dồi dào.")
            elif dep_growth > 0:
                report.append(f"Tiền gửi tăng nhẹ (+{dep_growth:.1f}%).")
            elif dep_growth > -5:
                report.append(f"Tiền gửi giảm nhẹ ({dep_growth:.1f}%).")
            else:
                report.append(f"⚠️ Tiền gửi giảm mạnh ({dep_growth:.1f}%) – Cần theo dõi.")
        else:
            report.append("Không có dữ liệu tiền gửi khách hàng.")
        
        # 3. ROE
        roe = get_safe_float(current, 'roe')
        if roe is not None:
            if roe > 18:
                report.append(f"ROE rất cao ({roe:.1f}%) – Hiệu quả sử dụng vốn xuất sắc.")
            elif roe > 15:
                report.append(f"ROE cao ({roe:.1f}%) – Hiệu quả tốt.")
            elif roe > 10:
                report.append(f"ROE trung bình ({roe:.1f}%).")
            else:
                report.append(f"⚠️ ROE thấp ({roe:.1f}%) – Hiệu quả sử dụng vốn yếu.")
        else:
            report.append("Không có dữ liệu ROE.")

        # 4. ROA
        roa = get_safe_float(current, 'roa')
        if roa is not None:
            if roa > 1.5:
                report.append(f"ROA cao ({roa:.2f}%) – Sinh lời từ tài sản tốt.")
            elif roa > 1:
                report.append(f"ROA ổn định ({roa:.2f}%).")
            else:
                report.append(f"⚠️ ROA thấp ({roa:.2f}%) – Sinh lời từ tài sản yếu.")
        else:
            report.append("Không có dữ liệu ROA.")

        return " • ".join(report) if report else "Dữ liệu cơ bản không đầy đủ."

    except Exception as e:
        # In lỗi chi tiết ra Terminal để bạn dễ sửa (quan trọng)
        print(f"🔥🔥 LỖI CƠ BẢN ({symbol}): {str(e)}")
        if cursor: cursor.close()
        return f"Lỗi: {str(e)}"
    
# ================== DỰ ĐOÁN CHÍNH ==================

def predict_trend(symbol, days_ahead=14):
    try:
        ticker = yf.Ticker(f"{symbol}.VN")
        df = ticker.history(period="2y")
        
        if len(df) < 100:
            return [], "Không đủ dữ liệu", "Chưa đủ lịch sử giá để phân tích.", 0

        close = df['Close']
        volume = df['Volume']

        # Tính các chỉ báo
        df['RSI'] = calculate_rsi(close)
        df['MA20'] = close.rolling(20).mean()
        df['MA50'] = close.rolling(50).mean()
        df['MA200'] = close.rolling(200).mean()
        df['MACD'], df['Signal'], df['Hist'] = calculate_macd(close)
        df['BB_Mid'], df['BB_Upper'], df['BB_Lower'] = calculate_bollinger_bands(close)
        df['Vol_MA20'] = volume.rolling(20).mean()

        current_price = close.iloc[-1]
        current_rsi = df['RSI'].iloc[-1]
        current_macd = df['MACD'].iloc[-1]
        current_signal = df['Signal'].iloc[-1]
        vol_today = volume.iloc[-1]
        vol_ma20 = df['Vol_MA20'].iloc[-1]

        # Dự báo giá
        recent = df.tail(60).reset_index()
        recent['Ordinal'] = recent['Date'].map(pd.Timestamp.toordinal)
        X = recent[['Ordinal']]
        y = recent['Close']
        
        from sklearn.linear_model import LinearRegression
        model = LinearRegression()
        model.fit(X, y)

        last_date = recent['Date'].iloc[-1]
        future_dates = []
        future_ordinal = []
        for i in range(1, days_ahead + 10):
            next_date = last_date + timedelta(days=i)
            if next_date.weekday() < 5:
                future_dates.append(next_date)
                future_ordinal.append([next_date.toordinal()])
                if len(future_dates) == days_ahead:
                    break

        predictions = model.predict(pd.DataFrame(future_ordinal, columns=['Ordinal']))
        pct_change = (predictions[-1] - current_price) / current_price * 100

        # Xác định xu hướng
        if pct_change > 5:
            trend = "TĂNG MẠNH"
        elif pct_change > 1.5:
            trend = "TĂNG NHẸ"
        elif pct_change > -1.5:
            trend = "ĐI NGANG"
        elif pct_change > -5:
            trend = "GIẢM NHẸ"
        else:
            trend = "GIẢM MẠNH"

        score = 50  

        # Dự báo giá
        if pct_change > 5: score += 30
        elif pct_change > 1.5: score += 15
        elif pct_change > -1.5: score += 0
        elif pct_change > -5: score -= 15
        else: score -= 30

        if current_rsi < 30: score += 15
        elif current_rsi > 70: score -= 15

        if current_price > df['MA20'].iloc[-1]: score += 10
        if df['MA50'].iloc[-1] > df['MA200'].iloc[-1]: score += 20

        if current_macd > current_signal and df['Hist'].iloc[-1] > df['Hist'].iloc[-2]: score += 20

        if current_price < df['BB_Lower'].iloc[-1]: score += 10
        elif current_price > df['BB_Upper'].iloc[-1]: score -= 10

        if vol_today > vol_ma20 * 1.5: score += 15

        fund_reasons = get_fundamental_analysis(symbol).split(" • ")
        for r in fund_reasons:
            if "tăng mạnh" in r or "cao" in r or "xuất sắc" in r: score += 10
            elif "tăng nhẹ" in r: score += 5
            elif "giảm nhẹ" in r: score -= 5
            elif "giảm mạnh" in r or "thấp" in r or "yếu" in r: score -= 15

        score = max(0, min(100, score))

        # Reasons
        reasons = [f"Dự báo {trend} {abs(pct_change):.1f}% trong {days_ahead} ngày tới."]
        if current_rsi > 70: reasons.append("RSI > 70 → Quá mua, có thể điều chỉnh giảm.")
        elif current_rsi < 30: reasons.append("RSI < 30 → Quá bán, cơ hội bật tăng.")
        if current_price > df['MA20'].iloc[-1]: reasons.append("Giá trên MA20 → Xu hướng ngắn hạn tích cực.")
        if df['MA50'].iloc[-1] > df['MA200'].iloc[-1]: reasons.append("Golden Cross (MA50 > MA200) → Xu hướng dài hạn TĂNG.")
        if current_macd > current_signal and df['Hist'].iloc[-1] > df['Hist'].iloc[-2]: reasons.append("MACD cắt lên + Histogram dương → Tín hiệu MUA mạnh.")
        if current_price < df['BB_Lower'].iloc[-1]: reasons.append("Giá chạm dải dưới Bollinger → Có thể bật tăng.")
        elif current_price > df['BB_Upper'].iloc[-1]: reasons.append("Giá chạm dải trên Bollinger → Cảnh báo quá mua.")
        if vol_today > vol_ma20 * 1.5: reasons.append("Khối lượng bùng nổ (>1.5x trung bình) → Xác nhận xu hướng.")
        reasons.append(f"[Cơ bản] {get_fundamental_analysis(symbol)}")

        final_reason = " • ".join(reasons)

        chart_data = [{"time": last_date.strftime('%Y-%m-%d'), "value": float(current_price)}]
        for date, pred in zip(future_dates, predictions):
            chart_data.append({"time": date.strftime('%Y-%m-%d'), "value": float(pred)})

        return chart_data, trend, final_reason, round(score)

    except Exception as e:
        print(f"AI Error: {e}")
        return [], "Lỗi hệ thống", f"Không thể phân tích do lỗi: {str(e)}", 0