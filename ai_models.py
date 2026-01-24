# ai_models.py
import numpy as np
import os
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import SimpleRNN, Dense, Dropout

class StockRNN:
    def __init__(self, symbol):
        self.symbol = symbol
        self.model = None
        self.model_path = f'models_ai/{symbol}_rnn.keras'

    def build_model(self, input_shape):
        """
        Xây dựng kiến trúc SimpleRNN.
        Input shape: (60, 6) - 60 ngày quá khứ, 6 đặc trưng
        """
        self.model = Sequential()
        
        # Layer 1: SimpleRNN (Thay vì LSTM)
        # SimpleRNN tính toán nhanh hơn nhưng ghi nhớ dài hạn kém hơn LSTM
        self.model.add(SimpleRNN(units=50, return_sequences=True, input_shape=input_shape))
        self.model.add(Dropout(0.2))
        
        # Layer 2
        self.model.add(SimpleRNN(units=50, return_sequences=False))
        self.model.add(Dropout(0.2))
        
        # Output
        self.model.add(Dense(units=1))
        
        self.model.compile(optimizer='adam', loss='mean_squared_error')
        return self.model

    def train(self, X_train, y_train, epochs=5, batch_size=32):
        if self.model is None:
            self.build_model((X_train.shape[1], X_train.shape[2]))
            
        print(f"   🌊 [RNN] Đang train model cho {self.symbol}...")
        history = self.model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size, verbose=0)
        return history

    def save_model(self):
        if not os.path.exists('models_ai'):
            os.makedirs('models_ai')
        if self.model:
            self.model.save(self.model_path)
            print(f"   💾 [RNN] Đã lưu: {self.model_path}")

    def load_model(self):
        if os.path.exists(self.model_path):
            self.model = load_model(self.model_path)
            return True
        return False

    def predict(self, input_data):
        """
        input_data: Scaled numpy array shape (1, 60, 6)
        """
        if self.model is None:
            loaded = self.load_model()
            if not loaded: return None
            
        return self.model.predict(input_data)