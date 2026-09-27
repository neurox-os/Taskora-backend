from database import Base, get_db, engine
from models import User
from sqlalchemy.orm import Session
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Annotated
import auth
import task
from dotenv import load_dotenv 
import os
load_dotenv()

app = FastAPI()

origins =os.getenv("URL"),


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           
    allow_credentials=True,           
    allow_methods=["*"],              
    allow_headers=["*"],             
)

app.include_router(auth.router)
app.include_router(task.task)

Base.metadata.create_all(engine)

db_dependency = Annotated[Session, Depends(get_db)]



