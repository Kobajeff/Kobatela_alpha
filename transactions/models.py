from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime
from config.settings import engine as db_engine
from models.base import Base 
from users.users import User  # Assurez-vous que `users` est bien importé AVANT `transactions`



class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    status = Column(String(20), nullable=False, default="pending")  # pending, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Transaction(id={self.id}, sender={self.sender_id or 'N/A'}, receiver={self.receiver_id or 'N/A'}, amount={self.amount}, status={self.status})>"
    
# Créer une session locale
SessionLocal = sessionmaker(bind=db_engine)
# Function to get a new session
def get_session():
    return SessionLocal()

# Créer la base de données et les tables si elles n'existent pas encore

Base.metadata.create_all(bind=db_engine)