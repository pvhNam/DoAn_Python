from enum import Enum # dung enum de liet ke cac hang so de dung tranh sai va ngay phan cong lai

class OrderType(Enum):
    MARKET = "MARKET" # mua gia o hien tai
    LIMIT = "LIMIT" # mua / ban minh tu chinh

class OrderSide(Enum):
    BUY ="BUY"
    SELL = "SELL" # basn 

class OrderStatus(Enum):
    PENDING = "PENDING" # lenh dang cho 
    FILLED = "FILLED" # khop lenh
    CANCELLED = "CANCELLED" #huy 
    REJECTED = "REJECTED" # bi tu choi khong mua duoc

@dataclass
class Trade:
    id:str
    order_id: str # lien ket voi order
    symbol: str 
    price: float # gia khop
    quantity: int  # so luong khop 
    commission: float #phi giao dich
    executed_at: datetime 