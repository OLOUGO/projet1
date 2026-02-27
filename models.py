from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(200))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True)
    category = Column(String(50))
    unit = Column(String(20))
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    stocks = relationship("Stock", back_populates="product")
    prices = relationship("Price", back_populates="product")
    creator = relationship("User")

class Zone(Base):
    __tablename__ = "zones"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), index=True)
    type = Column(String(50))
    department = Column(String(50))
    city = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    
    stocks = relationship("Stock", back_populates="zone")
    prices = relationship("Price", back_populates="zone")

class Stock(Base):
    __tablename__ = "stocks"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    zone_id = Column(Integer, ForeignKey("zones.id"))
    quantity = Column(Float)
    date = Column(DateTime, default=datetime.now)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    product = relationship("Product", back_populates="stocks")
    zone = relationship("Zone", back_populates="stocks")
    creator = relationship("User")

class Price(Base):
    __tablename__ = "prices"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"))
    zone_id = Column(Integer, ForeignKey("zones.id"))
    price = Column(Float)
    date = Column(DateTime, default=datetime.now)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    product = relationship("Product", back_populates="prices")
    zone = relationship("Zone", back_populates="prices")
    creator = relationship("User")