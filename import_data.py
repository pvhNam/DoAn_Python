import pandas as pd
import glob
import os
from flask import Flask
from models.database import get_db

app = Flask(__name__)

def clean_number(val):
    """Làm sạch số liệu"""
    try:
        s = str(val).strip()
        if s in ['-', '', 'nan', 'NaN', 'None']: return 0
        return float(s.replace(',', '').replace('.', ''))
    except:
        return 0

def find_header_index(df_head):
    """Tìm xem dòng tiêu đề nằm ở đâu (Tìm dòng có chữ 'Chỉ tiêu' hoặc 'Mã số')"""
    for idx, row in df_head.iterrows():
        row_str = " ".join(row.astype(str)).lower()
        if 'chỉ tiêu' in row_str or 'mã số' in row_str or 'tài sản' in row_str:
            return idx
    return 10 # Mặc định nếu không tìm thấy

def process_dataframe(df, symbol, sheet_type, cursor, count_success):
    try:
        # Cột đầu tiên thường là tên chỉ tiêu
        first_col = df.columns[0]
        
        # 1. NẾU LÀ KẾT QUẢ KINH DOANH -> TÌM LỢI NHUẬN
        if sheet_type == 'KQKD':
            # Tìm dòng có chữ "Lợi nhuận sau thuế"
            rows = df[df[first_col].astype(str).str.contains("Lợi nhuận sau thuế", case=False, na=False)]
            if not rows.empty:
                row = rows.iloc[0]
                print(f"      ✅ [KQKD] Tìm thấy Lợi nhuận của {symbol}")
                
                for col in df.columns:
                    # Duyệt qua các cột Năm (2020, 2021...)
                    if str(col).strip().isdigit() and int(str(col).strip()) > 2000:
                        year = int(str(col).strip())
                        val = clean_number(row[col])
                        
                        if val != 0:
                            sql = """
                                INSERT INTO financial_data (symbol, year, profit) 
                                VALUES (%s, %s, %s) 
                                ON DUPLICATE KEY UPDATE profit = VALUES(profit)
                            """
                            cursor.execute(sql, (symbol, year, val))
                            count_success[0] += 1

        # 2. NẾU LÀ CÂN ĐỐI KẾ TOÁN -> TÌM TÀI SẢN
        elif sheet_type == 'CDKT':
            # Tìm dòng "Tổng tài sản"
            rows = df[df[first_col].astype(str).str.contains("Tổng tài sản", case=False, na=False)]
            if not rows.empty:
                row = rows.iloc[0]
                print(f"      ✅ [CDKT] Tìm thấy Tổng tài sản của {symbol}")
                
                for col in df.columns:
                    if str(col).strip().isdigit() and int(str(col).strip()) > 2000:
                        year = int(str(col).strip())
                        val = clean_number(row[col])
                        
                        if val != 0:
                            sql = """
                                INSERT INTO financial_data (symbol, year, assets) 
                                VALUES (%s, %s, %s) 
                                ON DUPLICATE KEY UPDATE assets = VALUES(assets)
                            """
                            cursor.execute(sql, (symbol, year, val))
                            count_success[0] += 1
                            
    except Exception as e:
        print(f"      ⚠️ Lỗi xử lý data: {e}")

def import_fiinpro_v4():
    conn = get_db()
    cursor = conn.cursor()
    
    # Tìm cả file excel và csv
    files = glob.glob("*.xlsx") + glob.glob("*.csv")
    print(f"🔍 Tìm thấy {len(files)} file.")
    
    count_success = [0] # Dùng list để lưu biến đếm
    
    # Danh sách mã ngân hàng cần quét
    BANK_LIST = [
        'VIB', 'VCB', 'TCB', 'VPB', 'TPB', 'MBB', 'ACB', 'BID', 'CTG', 
        'VAB', 'STB', 'HDB', 'LPB', 'MSB', 'SSB', 'EIB', 'OCB', 'SHB', 
        'NAB', 'ABB', 'BAB', 'BVB', 'KLB', 'NVB', 'PGB', 'SGB', 'AGRB'
    ]

    for filepath in files:
        filename = os.path.basename(filepath)
        if filename.startswith('import_data') or filename.startswith('~$'): continue

        # 1. Xác định Mã CK từ tên file
        symbol = None
        for s in BANK_LIST:
            if s in filename:
                symbol = s
                break
        
        if not symbol: 
            # print(f"⚠️ Bỏ qua: {filename} (Không rõ mã CK)")
            continue

        print(f"\n📂 Đang quét: {filename} -> Mã: {symbol}")

        try:
            # --- TRƯỜNG HỢP 1: FILE EXCEL (XLSX) ---
            if filepath.endswith('.xlsx'):
                # Mở file excel
                xl = pd.ExcelFile(filepath)
                # Duyệt qua từng Sheet (Trang tính)
                for sheet_name in xl.sheet_names:
                    sheet_lower = sheet_name.lower()
                    
                    # Xác định loại sheet
                    sheet_type = None
                    if 'kết quả kinh doanh' in sheet_lower or 'kqkd' in sheet_lower:
                        sheet_type = 'KQKD'
                    elif 'cân đối kế toán' in sheet_lower or 'cdkt' in sheet_lower:
                        sheet_type = 'CDKT'
                    
                    if sheet_type:
                        # Tìm dòng header (thường là dòng 10-11)
                        df_preview = pd.read_excel(filepath, sheet_name=sheet_name, nrows=20, header=None)
                        header_idx = find_header_index(df_preview)
                        
                        # Đọc dữ liệu thật
                        df = pd.read_excel(filepath, sheet_name=sheet_name, header=header_idx)
                        process_dataframe(df, symbol, sheet_type, cursor, count_success)

            # --- TRƯỜNG HỢP 2: FILE CSV (Nếu có) ---
            elif filepath.endswith('.csv'):
                sheet_type = None
                if 'Kết quả kinh doanh' in filename: sheet_type = 'KQKD'
                elif 'Bảng cân đối kế toán' in filename: sheet_type = 'CDKT'
                
                if sheet_type:
                    try:
                        df = pd.read_csv(filepath, header=10, encoding='utf-8')
                    except:
                        df = pd.read_csv(filepath, header=10, encoding='utf-16', sep='\t')
                    process_dataframe(df, symbol, sheet_type, cursor, count_success)

        except Exception as e:
            print(f"   ❌ Lỗi đọc file: {e}")

    conn.commit()
    cursor.close()
    conn.close()
    print(f"\n🚀 HOÀN TẤT! Đã cập nhật thành công {count_success[0]} dữ liệu vào Database.")

if __name__ == "__main__":
    with app.app_context():
        import_fiinpro_v4()