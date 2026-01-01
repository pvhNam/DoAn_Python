import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression

<<<<<<< Updated upstream
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
=======
# ================== 1. CÁC HÀM TÍNH TOÁN (CORE) ==================

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
    hist = macd - signal_line
    return macd, signal_line, hist

def calculate_bollinger_bands(series, window=20, num_std=2):
    mid = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return mid, upper, lower

def calculate_ichimoku(df):
    high_9 = df['High'].rolling(window=9).max()
    low_9 = df['Low'].rolling(window=9).min()
    df['tenkan_sen'] = (high_9 + low_9) / 2

    high_26 = df['High'].rolling(window=26).max()
    low_26 = df['Low'].rolling(window=26).min()
    df['kijun_sen'] = (high_26 + low_26) / 2

    df['senkou_span_a'] = ((df['tenkan_sen'] + df['kijun_sen']) / 2).shift(26)

    high_52 = df['High'].rolling(window=52).max()
    low_52 = df['Low'].rolling(window=52).min()
    df['senkou_span_b'] = ((high_52 + low_52) / 2).shift(26)
    
    return df

def identify_candlestick_pattern(row, prev_row):
    """Nhận diện mô hình nến đơn giản"""
    open_p, close_p = row['Open'], row['Close']
    high_p, low_p = row['High'], row['Low']
    
    body = abs(close_p - open_p)
    upper_wick = high_p - max(open_p, close_p)
    lower_wick = min(open_p, close_p) - low_p
    
    pattern = "Không rõ ràng"
    
    # Doji
    if body <= (high_p - low_p) * 0.1:
        pattern = "Doji (Lưỡng lự)"
    # Hammer / Hanging Man
    elif lower_wick > body * 2 and upper_wick < body * 0.5:
        pattern = "Hammer/Pinbar (Đảo chiều)"
    # Marubozu
    elif body > (high_p - low_p) * 0.9:
        pattern = "Marubozu (Lực mạnh)"
    
    return pattern

# ================== 2. HÀM PHÂN TÍCH CHUYÊN GIA ==================
>>>>>>> Stashed changes

# HÀM DỰ ĐOÁN CHÍNH
def predict_trend(symbol, days_ahead=14):
    try:
<<<<<<< Updated upstream
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
=======
        # --- LẤY DỮ LIỆU ---
        ticker = yf.Ticker(f"{symbol}.VN")
        df = ticker.history(period="1y") # Lấy 1 năm để tính kháng cự/hỗ trợ chuẩn
        
        if len(df) < 100:
            return [], "Không đủ dữ liệu", "Cần thêm lịch sử giao dịch để phân tích.", 0

        # --- TÍNH TOÁN CHỈ SỐ ---
        close = df['Close']
        df['RSI'] = calculate_rsi(close)
        df['MA20'] = close.rolling(20).mean()
        df['MA50'] = close.rolling(50).mean()
        df['MA200'] = close.rolling(200).mean()
        df['MACD'], df['Signal'], df['Hist'] = calculate_macd(close)
        df['BB_Mid'], df['BB_Upper'], df['BB_Lower'] = calculate_bollinger_bands(close)
        df = calculate_ichimoku(df)

        # Lấy giá trị hiện tại
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        price = curr['Close']
        
        # --- 1. XÁC ĐỊNH XU HƯỚNG (TREND) ---
        trend_status = "Đi ngang (Sideway)"
        trend_expl = "Giá dao động trong biên độ hẹp."
        
        if price > curr['MA20'] and curr['MA20'] > curr['MA50']:
            trend_status = "Tăng (Uptrend)"
            trend_expl = "Giá nằm trên MA20 và MA50, cấu trúc đỉnh đáy nâng dần."
        elif price < curr['MA20'] and curr['MA20'] < curr['MA50']:
            trend_status = "Giảm (Downtrend)"
            trend_expl = "Giá nằm dưới các đường trung bình động ngắn hạn."
        
        # --- 2. XÁC ĐỊNH HỖ TRỢ / KHÁNG CỰ (60 phiên gần nhất) ---
        recent_df = df.tail(60)
        support_level = recent_df['Low'].min()
        resistance_level = recent_df['High'].max()
        
        nearest_lvl = ""
        if (price - support_level) < (resistance_level - price):
            nearest_lvl = f"Giá đang gần vùng hỗ trợ cứng {support_level:,.0f}."
        else:
            nearest_lvl = f"Giá đang tiệm cận kháng cự đỉnh cũ {resistance_level:,.0f}."

        # --- 3. MÔ HÌNH & TÍN HIỆU KỸ THUẬT ---
        signals = []
        
        # Ichimoku
        cloud_top = max(curr['senkou_span_a'], curr['senkou_span_b'])
        if price > cloud_top: signals.append("Giá vượt mây Ichimoku (Tích cực)")
        elif price < min(curr['senkou_span_a'], curr['senkou_span_b']): signals.append("Giá dưới mây (Tiêu cực)")
        
        # RSI
        if curr['RSI'] > 70: signals.append(f"RSI={curr['RSI']:.0f} (Vùng Quá mua)")
        elif curr['RSI'] < 30: signals.append(f"RSI={curr['RSI']:.0f} (Vùng Quá bán)")
        else: signals.append(f"RSI={curr['RSI']:.0f} (Trung tính)")
        
        # MACD
        if curr['MACD'] > curr['Signal']: signals.append("MACD cắt lên Signal")
        else: signals.append("MACD cắt xuống Signal")
        
        # Nến Nhật
        candle_pattern = identify_candlestick_pattern(curr, prev)
        
        # --- 4. TÍNH ĐIỂM & KHUYẾN NGHỊ ---
        score = 50
        if trend_status.startswith("Tăng"): score += 20
        elif trend_status.startswith("Giảm"): score -= 20
        
        if curr['RSI'] < 30: score += 15
        elif curr['RSI'] > 70: score -= 15
        
        if curr['MACD'] > curr['Signal']: score += 10
        
        recommendation = "QUAN SÁT"
        reason_short = "Thị trường chưa rõ xu hướng, cần chờ tín hiệu xác nhận."
        
        if score >= 75:
            recommendation = "MUA (BUY)"
            reason_short = "Xu hướng tăng mạnh kết hợp dòng tiền tốt."
        elif score >= 60:
            recommendation = "MUA THĂM DÒ"
            reason_short = "Tín hiệu tích cực nhưng cần quản trị rủi ro."
        elif score <= 25:
            recommendation = "BÁN (SELL)"
            reason_short = "Vi phạm các ngưỡng hỗ trợ, động lượng yếu."
        elif score <= 40:
            recommendation = "HẠ TỶ TRỌNG"
            reason_short = "Rủi ro điều chỉnh cao."

        # --- 5. TẠO FORMAT VĂN BẢN (GEMINI STYLE) ---
        # Sử dụng HTML <br> để xuống dòng trong giao diện web
        
        analysis_text = f"""
        <b>• Xu hướng hiện tại:</b> {trend_status}.<br>
        <i>({trend_expl})</i><br><br>
        
        <b>• Hỗ trợ & Kháng cự:</b><br>
        - Hỗ trợ gần nhất: <b>{support_level:,.0f}</b><br>
        - Kháng cự quan trọng: <b>{resistance_level:,.0f}</b><br>
        - Nhận định: {nearest_lvl}<br><br>
        
        <b>• Tín hiệu kỹ thuật & Mô hình:</b><br>
        - Mẫu hình nến hôm nay: {candle_pattern}<br>
        - Các chỉ báo: {', '.join(signals)}.<br><br>
        
        <b>• Khuyến nghị chuyên gia:</b> <span class="badge bg-warning text-dark">{recommendation}</span><br>
        Lý do: {reason_short}
        """

        # --- 6. DỰ BÁO BIỂU ĐỒ (GIỮ NGUYÊN CODE CŨ) ---
        # (Đoạn này dùng Linear Regression để vẽ đường dự báo trên chart)
        recent = df.tail(60).reset_index()
        recent['Ordinal'] = recent['Date'].apply(lambda x: x.toordinal())
        X = recent[['Ordinal']]
        y = recent['Close']
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
                if len(future_dates) == days_ahead: break
                
        predictions = model.predict(pd.DataFrame(future_ordinal, columns=['Ordinal']))
        
        chart_data = [{"time": last_date.strftime('%Y-%m-%d'), "value": float(price)}]
        for date, pred in zip(future_dates, predictions):
            chart_data.append({"time": date.strftime('%Y-%m-%d'), "value": float(pred)})

        # Trả về kết quả
        # Lưu ý: 'trend_status' ở đây dùng làm title ngắn, 'analysis_text' là nội dung dài
        return chart_data, trend_status.split(" ")[0].upper(), analysis_text, round(score)

    except Exception as e:
        print(f"Lỗi Analysis: {e}")
        return [], "LỖI", "Không thể phân tích dữ liệu.", 0
>>>>>>> Stashed changes
