import pandas as pd
import re
from flask import Flask
from models.database import get_db  # Giữ nguyên nếu bạn dùng Flask

app = Flask(__name__)

def clean_number(val):
    if pd.isna(val) or val in ['-', '', 'nan', 'NaN', 'None', None]:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    s = str(val).strip()
    
    if '(' in s and ')' in s:
        s = '-' + s.replace('(', '').replace(')', '')
    
    s = re.sub(r'[^\d.,-]', '', s)
    
    if '.' in s and ',' in s:
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    elif s.count('.') > 1:
        s = s.replace('.', '')
    
    try:
        return float(s)
    except:
        return 0.0

def import_full_fundamentals(file_path="data_loc_30_ma_full_format.xlsx"):
    conn = get_db()
    cursor = conn.cursor()
    
    count_success = 0
    count_matched = 0

    xl = pd.ExcelFile(file_path)
    print(f"Đang import dữ liệu THEO NĂM từ file: {file_path} - Có {len(xl.sheet_names)} cổ phiếu\n")

    indicators_mapping = {
        'tổng tài sản': 'total_assets',
        'tổng cộng tài sản': 'total_assets',
        
        'tài sản ngắn hạn': 'current_assets',
        'tài sản lưu động': 'current_assets',
        'tài sản ngắn hạn và đầu tư ngắn hạn': 'current_assets',
        
        'tiền và tương đương tiền': 'cash_equiv',
        'tiền và các khoản tương đương tiền': 'cash_equiv',
        
        'các khoản phải thu': 'receivables',
        'phải thu ngắn hạn': 'receivables',
        'phải thu của khách hàng': 'receivables',
        
        'hàng tồn kho': 'inventory',
        
        'tài sản cố định': 'fixed_assets',
        'tài sản dài hạn': 'long_term_assets',
        'đầu tư tài chính dài hạn': 'long_term_investments',
        'bất động sản đầu tư': 'investment_property',
        
        'nợ phải trả': 'total_liabilities',
        'tổng nợ phải trả': 'total_liabilities',
        
        'nợ ngắn hạn': 'short_term_liabilities',
        'phải trả ngắn hạn': 'short_term_liabilities',
        'vay và nợ ngắn hạn': 'short_term_borrowings',
        'vay ngắn hạn': 'short_term_borrowings',
        
        'nợ dài hạn': 'long_term_liabilities',
        'vay dài hạn': 'long_term_borrowings',
        
        'vốn chủ sở hữu': 'equity',
        'vốn chủ sở hữu của công ty mẹ': 'equity',
        'lợi nhuận sau thuế chưa phân phối': 'retained_earnings',
        
        'tiền gửi khách hàng': 'customer_deposits',
        'tiền gửi của khách hàng': 'customer_deposits',
        'cho vay khách hàng': 'customer_loans',
        'dư nợ cho vay': 'customer_loans',
        
        'doanh thu thuần': 'revenue',
        'doanh thu bán hàng và cung cấp dịch vụ': 'revenue',
        'lợi nhuận gộp': 'gross_profit',
        'lợi nhuận thuần từ hoạt động kinh doanh': 'operating_profit',
        'chi phí tài chính': 'finance_expense',
        'lợi nhuận trước thuế': 'profit_before_tax',
        'lợi nhuận sau thuế': 'net_profit',
        'lợi nhuận sau thuế công ty mẹ': 'parent_net_profit',
        'roe': 'roe',
        'roa': 'roa',
        'eps': 'eps',
        'p/e': 'pe',
        'p/b': 'pb',
    }

    for sheet_name in xl.sheet_names:
        symbol = sheet_name.strip().upper()
        print(f"→ Đang xử lý: {symbol}")

        df_raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
        header_row_idx = None
        for idx, row in df_raw.iterrows():
            if row.astype(str).str.contains('Kỳ báo cáo', case=False, na=False).any():
                header_row_idx = idx
                break
        if header_row_idx is None:
            print(f"   Không tìm thấy 'Kỳ báo cáo' → Bỏ qua {symbol}")
            continue

        df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_row_idx)
        df.iloc[:, 0] = df.iloc[:, 0].astype(str).str.lower().str.replace('\n', ' ').str.strip()

        data_df = df.iloc[3:].copy()
        data_df = data_df[data_df.iloc[:, 0].str.len() > 0]
        data_df.reset_index(drop=True, inplace=True)

        local_matched = 0
        for _, row in data_df.iterrows():
            raw_name = str(row.iloc[0])
            indicator_name = raw_name.lower().strip()

            if indicator_name in ['nan', '', 'mã cp', 'cir', 'car', 'casa', 'mã năm tỷ lệ']:
                continue

            # Match với ưu tiên từ khóa dài nhất
            matched_field = None
            best_length = 0
            for key_phrase, field in indicators_mapping.items():
                if key_phrase in indicator_name and len(key_phrase) > best_length:
                    matched_field = field
                    best_length = len(key_phrase)

            if not matched_field:
                continue

            local_matched += 1
            count_matched += 1

            # === CHỈ LẤY CỘT NĂM (là số nguyên thuần) ===
            for col_idx in range(1, len(df.columns)):
                col_name = str(df.columns[col_idx]).strip()

                # Điều kiện nghiêm ngặt: chỉ chấp nhận cột là số năm (2017 đến 2030), không có chữ cái hay dấu gạch
                if col_name.isdigit() and 2017 <= int(col_name) <= 2030:
                    year = int(col_name)
                else:
                    continue  # Bỏ qua hoàn toàn cột quý như "2024-Q1", "2024Q2",...

                val = clean_number(row.iloc[col_idx])
                if val == 0:
                    continue

                sql = f"""
                    INSERT INTO financial_data_coban (symbol, year, {matched_field})
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE {matched_field} = VALUES({matched_field})
                """
                try:
                    cursor.execute(sql, (symbol, year, val))
                    count_success += 1
                except Exception as e:
                    print(f"   Lỗi insert {symbol} {year} {matched_field}: {e}")

        print(f"   Đã match {local_matched} chỉ tiêu (chỉ năm) cho {symbol}")

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\nHOÀN TẤT IMPORT CHỈ DỮ LIỆU NĂM!")
    print(f"   → Đã insert thành công {count_success} giá trị.")
    print(f"   → Tổng cộng match được {count_matched} chỉ tiêu từ các năm.")

if __name__ == "__main__":
    with app.app_context():
        import_full_fundamentals("data_loc_30_ma_full_format.xlsx")