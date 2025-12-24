
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print(f"🔑 API Key đang dùng: {api_key[:5]}...{api_key[-5:] if api_key else 'None'}")

if not api_key:
    print("❌ LỖI: Không tìm thấy API Key.")
    exit()

genai.configure(api_key=api_key)

print("\n--- 1. Kiểm tra danh sách Model ---")
try:
    print("Đang kết nối tới Google...")
    found_flash = False
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ Tìm thấy: {m.name}")
            if "gemini-1.5-flash" in m.name:
                found_flash = True
    
    if not found_flash:
        print("⚠️ CẢNH BÁO: Không thấy gemini-1.5-flash trong danh sách trả về!")
    else:
        print("🌟 OK: Tài khoản của bạn có quyền dùng gemini-1.5-flash")

except Exception as e:
    print(f"❌ Lỗi nghiêm trọng khi list_models: {e}")
    print("👉 Gợi ý: API Key sai hoặc chưa kích hoạt Google AI Studio.")

print("\n--- 2. Test thử Text Generation ---")
try:
    model = genai.GenerativeModel("gemini-1.5-flash")
    response = model.generate_content("Chào Gemini, bạn có hoạt động không?")
    print(f"🤖 Phản hồi: {response.text}")
except Exception as e:
    print(f"❌ Lỗi Generation: {e}")