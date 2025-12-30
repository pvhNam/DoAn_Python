import math
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense, LSTM

# 1. TẢI DỮ LIỆU
# ---------------------------------------------------------
print("Đang tải dữ liệu...")
# Tải dữ liệu Apple (AAPL) từ 2016 đến 2021
stock_data = yf.download('AAPL', start='2016-01-01', end='2021-10-01')

# Kiểm tra nếu tải về bị lỗi index (MultiIndex) thì làm phẳng
if isinstance(stock_data.columns, pd.MultiIndex):
    stock_data.columns = stock_data.columns.get_level_values(0)

print(stock_data.head())

# Vẽ biểu đồ giá gốc
plt.figure(figsize=(15, 8))
plt.title('Lịch sử giá đóng cửa (Close Price)')
plt.plot(stock_data['Close'])
plt.xlabel('Ngày')
plt.ylabel('Giá ($)')
plt.show()

# 2. XỬ LÝ DỮ LIỆU (PRE-PROCESSING)
# ---------------------------------------------------------
# Chỉ lấy cột Close
close_prices = stock_data['Close']
values = close_prices.values.reshape(-1, 1) # Chuyển thành ma trận 2D (n dòng, 1 cột)

# Chia tập train (80%)
training_data_len = math.ceil(len(values) * 0.8)

# Scale dữ liệu về khoảng 0-1
scaler = MinMaxScaler(feature_range=(0, 1))
scaled_data = scaler.fit_transform(values)

# Tạo tập Train
train_data = scaled_data[0:training_data_len, :]
x_train = []
y_train = []

time_steps = 60 # Số ngày quá khứ dùng để dự đoán

for i in range(time_steps, len(train_data)):
    x_train.append(train_data[i-time_steps:i, 0])
    y_train.append(train_data[i, 0])

x_train, y_train = np.array(x_train), np.array(y_train)

# Reshape cho LSTM: [samples, time steps, features]
x_train = np.reshape(x_train, (x_train.shape[0], x_train.shape[1], 1))

# 3. XÂY DỰNG VÀ HUẤN LUYỆN MODEL
# ---------------------------------------------------------
model = Sequential()
model.add(LSTM(100, return_sequences=True, input_shape=(x_train.shape[1], 1)))
model.add(LSTM(100, return_sequences=False))
model.add(Dense(25))
model.add(Dense(1))

model.compile(optimizer='adam', loss='mean_squared_error')

print("Bắt đầu train model...")
model.fit(x_train, y_train, batch_size=1, epochs=20) # Tăng epochs nếu muốn chính xác hơn

# 4. KIỂM THỬ VÀ DỰ BÁO (TESTING)
# ---------------------------------------------------------
# Tạo tập Test
test_data = scaled_data[training_data_len - time_steps:, :]
x_test = []
y_test = values[training_data_len:] # Giá thực tế (đã reshape ở trên)

for i in range(time_steps, len(test_data)):
    x_test.append(test_data[i-time_steps:i, 0])

x_test = np.array(x_test)
x_test = np.reshape(x_test, (x_test.shape[0], x_test.shape[1], 1))

# Dự báo
predictions = model.predict(x_test)
predictions = scaler.inverse_transform(predictions) # Đưa về giá trị gốc

# 5. ĐÁNH GIÁ (RMSE)
# ---------------------------------------------------------
# Công thức RMSE chuẩn: Căn bậc hai của (Trung bình bình phương sai số)
rmse = np.sqrt(np.mean((predictions - y_test) ** 2))
print(f"RMSE (Sai số trung bình): {rmse}")

# 6. VẼ BIỂU ĐỒ KẾT QUẢ
# ---------------------------------------------------------
# Chuẩn bị dữ liệu để vẽ
data = stock_data.filter(['Close']) # Lấy dưới dạng DataFrame để tránh lỗi .columns
train = data[:training_data_len]
validation = data[training_data_len:].copy() # .copy() để tránh warning
validation['Predictions'] = predictions

plt.figure(figsize=(16, 8))
plt.title('Kết quả Dự báo Model LSTM')
plt.xlabel('Ngày')
plt.ylabel('Giá đóng cửa ($)')
plt.plot(train['Close'], label='Dữ liệu Train')
plt.plot(validation['Close'], label='Giá Thực tế (Val)')
plt.plot(validation['Predictions'], label='Giá Dự báo (AI)')
plt.legend(loc='lower right')
plt.grid(True, alpha=0.3)
plt.show()