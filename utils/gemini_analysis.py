# utils/gemini_analysis.py
import os
import base64
import tempfile
from dotenv import load_dotenv

from google import genai
from google.genai import types

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# THAY ĐỔI TẠI ĐÂY
MODEL_NAME = "gemini-2.5-flash"  # Hoặc "gemini-3-flash-preview" nếu muốn thử mới nhất

def analyze_chart_image(image_path: str, symbol: str) -> str:
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        prompt = f"""
Bạn là chuyên gia phân tích kỹ thuật chứng khoán Việt Nam với hơn 10 năm kinh nghiệm.
Hãy xem kỹ biểu đồ nến Nhật của cổ phiếu {symbol.upper()} trong ảnh và trả về phân tích ngắn gọn, chuyên nghiệp bằng tiếng Việt:

• Xu hướng hiện tại: Tăng / Giảm / Đi ngang (giải thích ngắn)
• Mức hỗ trợ và kháng cự quan trọng nhất
• Mô hình giá đang hình thành (nếu có): vai đầu vai, cờ, tam giác, đáy đôi, v.v.
• Tín hiệu từ chỉ báo kỹ thuật hiển thị trên chart (MA, RSI, MACD, Volume...)
• Khuyến nghị: Mua / Bán / Quan sát (kèm lý do ngắn gọn)

Trả về dưới dạng danh sách bullet points, không thêm lời chào hay kết thúc thừa.
        """

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type="image/png"
                )
            ]
        )

        return response.text.strip()

    except Exception as e:
        print(f"Lỗi Gemini: {e}")
        return "Gemini không thể phân tích biểu đồ lúc này. Vui lòng thử lại sau vài phút."