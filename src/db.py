
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker

DB_URL = 'sqlite:///guest_feedback.sqlite'
engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class Review(Base):
    __tablename__ = "reviews"
    id = Column(String(64), primary_key=True, index=True)
    outlet = Column(String(256), nullable=False)
    brand = Column(String(128), nullable=True)
    platform = Column(String(64), nullable=True)
    rating = Column(Integer, nullable=True)
    language = Column(String(8), nullable=True)
    text = Column(Text, nullable=False)
    timestamp = Column(String(64), nullable=True)
    username = Column(String(128), nullable=True)
    order_type = Column(String(64), nullable=True)

class Analysis(Base):
    __tablename__ = "analyses"
    id = Column(String(64), primary_key=True, index=True)  # review id
    sentiment = Column(String(16), nullable=False)
    topics = Column(Text, nullable=False)
    severity = Column(Integer, nullable=False)
    reply_en = Column(Text, nullable=False)
    reply_id = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="draft")  # draft|approved|exported

def init_db():
    Base.metadata.create_all(bind=engine)

def get_session():
    return SessionLocal()
