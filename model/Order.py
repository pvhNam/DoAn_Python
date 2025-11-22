@dataclass
class Order:
    id: str
    user_id: int
    symbol: str
    side: OrderSide # Mua hay Ban
    type: OrderType # Market hay Limit
    quantity: int   # So luong dat
    price: float    # Gia dat (neu la Limit)
    status: OrderStatus
    created_at: datetime