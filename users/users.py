from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from config.settings import engine as db_engine
from models.base import Base # Assurez-vous que `base` est bien importé AVANT `users`

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(100), nullable=False)

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

Base.metadata.create_all(bind=db_engine)