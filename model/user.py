from dataclasses import dataclass
from datetime import datetime

@dataclass
class user:
    id:int 
    username: str
    email:str
    password_hash:str #mat khau dung hash ma bam cho an toan ve mat khau 
    created_at: datetime

@datetime
class Wallet:
    user_id : int 
    currency: str # don vi tien te vnd usd
    balance: float # so tien hien co cua user
    locked_amount: float # tien khong dung duoc trong luc cho khop lenh 
    