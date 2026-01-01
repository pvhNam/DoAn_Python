import numpy as np
import pandas as pd
import joblib 
import os
from tensorflow.keras.models import load_model 
from models.database import get_db

# Đường dẫn thư mục chứa model
MODEL_DIR = 'models/ai_checkpoints'

def predict_with_lstm(symbol):
    """
    Hàm dự báo giá sử dụng Deep Learning (LSTM)
    Đã nâng cấp để trả về định dạng HTML chuyên nghiệp.
    """
    symbol = symbol.upper()
    
    # 1. Kiểm tra file Model và Scaler
    model_path = os.path.join(MODEL_DIR, f"{symbol}_lstm.h5")
    scaler_path = os.path.join(MODEL_DIR, f"{symbol}_scaler.pkl")

    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        return {
            "trend": "CHƯA CÓ AI",
            "reason": f"<i>Chưa có dữ liệu huấn luyện cho mã {symbol}. Vui lòng chạy train_ai.py trước.</i>",
            "next_price": 0
        }

    try:
        # 2. Load Model & Scaler
        model = load_model(model_path)
        scaler = joblib.load(scaler_path)

        # 3. Lấy dữ liệu từ DB (60 ngày gần nhất)
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        query = f"""
            SELECT close FROM stock_history 
            WHERE symbol = '{symbol}' 
            ORDER BY date DESC LIMIT 60
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        cursor.close()
        # Không đóng conn ở đây vì dùng chung pool (flask g)

        if len(rows) < 60:
            return {
                "trend": "THIẾU DATA",
                "reason": "Dữ liệu lịch sử không đủ 60 phiên để AI chạy dự báo.",
                "next_price": 0
            }

        # Sắp xếp lại theo thời gian tăng dần (Cũ -> Mới)
        data_last_60_days = np.array([r['close'] for r in reversed(rows)])
        
        # 4. Chuẩn hóa dữ liệu (Scaling)
        data_last_60_days = data_last_60_days.astype(float)
        current_price = float(data_last_60_days[-1]) # Giá hôm nay
        
        scaled_input = scaler.transform(data_last_60_days.reshape(-1, 1))
        x_input = np.reshape(scaled_input, (1, 60, 1))

        # 5. Dự đoán (Prediction)
        predicted_scaled_price = model.predict(x_input) 
        predicted_price = scaler.inverse_transform(predicted_scaled_price)
        final_price = float(predicted_price[0][0])

        # 6. PHÂN TÍCH KẾT QUẢ (LOGIC CHUYÊN GIA)
        percent_change = ((final_price - current_price) / current_price) * 100
        
        # --- Tạo nội dung nhận định dựa trên % ---
        trend = "THAM CHIẾU"
        color_class = "text-warning" # Màu vàng mặc định
        action = "QUAN SÁT"
        analysis_comment = ""

        # Tinh chỉnh ngưỡng (Thresholds) cho hợp lý hơn
        if percent_change > 4.0:
            trend = "TĂNG MẠNH"
            color_class = "text-success"
            action = "MUA GIA TĂNG"
            analysis_comment = "Mô hình nhận thấy xung lực tăng giá rất mạnh, khả năng bứt phá khỏi vùng đỉnh cũ."
        elif percent_change > 0.5:
            trend = "TĂNG NHẸ"
            color_class = "text-success"
            action = "NẮM GIỮ / MUA THĂM DÒ"
            analysis_comment = "Xu hướng phục hồi ngắn hạn, giá dự kiến đi lên từ từ."
        elif percent_change > -0.5:
            trend = "ĐI NGANG"
            color_class = "text-warning"
            action = "QUAN SÁT"
            analysis_comment = "Biên độ dao động dự báo thấp, chưa có tín hiệu bứt phá rõ ràng."
        elif percent_change > -4.0:
            trend = "GIẢM NHẸ"
            color_class = "text-danger"
            action = "HẠ TỶ TRỌNG"
            analysis_comment = "Áp lực điều chỉnh ngắn hạn, cân nhắc chốt lời hoặc giảm bớt vị thế."
        else:
            trend = "GIẢM MẠNH"
            color_class = "text-danger"
            action = "BÁN / CẮT LỖ"
            analysis_comment = "Cảnh báo rủi ro cao! AI dự báo đà giảm sâu, nên thoát hàng để bảo toàn vốn."

        # 7. FORMAT VĂN BẢN HTML (Giống analysis.py)
        # Tạo format số đẹp (ví dụ: +1.5% hoặc -2.1%)
        sign = "+" if percent_change > 0 else ""
        pct_str = f"{sign}{percent_change:.2f}%"

        reason_html = f"""
        <b>• Dự báo giá (T+1):</b> <span class="{color_class}" style="font-size: 1.1em; font-weight: bold;">{final_price:,.0f} VND</span><br>
        <b>• Biến động dự kiến:</b> <span class="{color_class}"><b>{pct_str}</b></span> so với giá hiện tại ({current_price:,.0f}).<br><br>
        
        <b>• Nhận định của AI:</b><br>
        <i>"{analysis_comment}"</i><br><br>
        
        <b>• Hành động khuyến nghị:</b> <span class="badge bg-primary">{action}</span>
        """

        return {
            "trend": trend,
            "reason": reason_html, # Trả về HTML thay vì text thường
            "next_price": final_price
        }

    except Exception as e:
        print(f"Lỗi AI Prediction {symbol}: {e}")
        return {
            "trend": "LỖI",
            "reason": f"Không thể dự báo do lỗi hệ thống: {str(e)}",
            "next_price": 0
        }