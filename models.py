from sqlalchemy import Column, Integer, String, ForeignKey, Boolean
from database import Base

class User(Base):
  __tablename__ = "user"
  id = Column(Integer, index=True, primary_key=True)
  username = Column(String, nullable=False)
  email = Column(String, unique=True, nullable=False)
  hash_password = Column(String, unique=True, nullable=False)

class Todo(Base):
  __tablename__ = "tasks"
  id = Column(Integer, index=True, primary_key=True)
  title = Column(String, nullable=False)
  description = Column(String, nullable=False)
  is_done = Column(Boolean, nullable=False, default=False)
  priority = Column(String, nullable=False)
  due = Column(String, nullable=False)
  user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"))