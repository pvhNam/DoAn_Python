@dataclass
class Stock:
    symbol: str # ma chung khoan 
    company_name: str # ten cong ty
    exchange: str # san chung khoan
    sector: str # loai nhu la thep, ngan hang, dau khi
@dataclass
class MarketCandle:
    symbol: str
    timestamp: datetime # moc thoi gian 
                        #vi du la cay nen 1 gio va timestamp la 9h 
                        # thi gia se bieu dien tu 9h toi 10h
    open: float #gia mo cua
    high: float # gia cao nhat
    low: float # gia thap nhat
    close:float # khoi luong
    volume:int # khoi luong giao dich