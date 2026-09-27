from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from database import get_db
from models import User
from typing import Annotated
from fastapi.security import OAuth2PasswordBearer
from schemas import New_User, Token, Login_User
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
import os
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
load_dotenv()

router = APIRouter(prefix="/auth", tags=["auth"])

db_dependency = Annotated[Session, Depends(get_db)]

ph = PasswordHasher(time_cost=3,memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
oauth2bearer = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

secret_key = os.getenv("SECRET_KEY")
algorithm = os.getenv("ALGORITHM")

def get_current_user(request : Request, token : Annotated[str, Depends(oauth2bearer)], db : db_dependency):
  if not token:
    token = request.cookies.get("access_token")
  if not token:
    raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Not authenticated"
        )
  try:
    payload = jwt.decode(token, secret_key, algorithms = [algorithm])
    email = payload.get('sub')
    token_type = payload.get('type')
    if email is None:
      raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate Credentials", headers={"WWW-Authenticate": "Bearer"})
    if token_type != 'access':
      raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    
  except ExpiredSignatureError:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired", headers={"WWW-Authenticate": "Bearer"})
  
  except InvalidTokenError:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate Credentials", headers={"WWW-Authenticate": "Bearer"})
  user = db.query(User).filter(User.email == email).first()
  
  if user is None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User Not Found")
  
  return user
  
def create_token(email : str, time : timedelta, token_type : str):
  expire = datetime.now(timezone.utc) + time
  encode = {'sub' : email,
            'exp' : expire,
            'type': token_type}
  return jwt.encode(encode, secret_key, algorithm=algorithm)

def authenticate_user(email : str, password : str, db : db_dependency):
  user = db.query(User).filter(User.email == email).first()
  
  if user is None:
    return None

  try:
    ph.verify(user.hash_password, password)
    return user
  except VerifyMismatchError:
    return None

@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
async def create_account(user : New_User, db : db_dependency,  response : Response):
  
  existing_email = db.query(User).filter(User.email == user.email).first()
  
  if existing_email:
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered. Please login")
  
  new_user = User(username=user.username, email=user.email, hash_password=ph.hash(user.password))
  
  db.add(new_user)
  db.commit()
  db.refresh(new_user)
  
  token = create_token(new_user.email, timedelta(minutes=10), "access")
  refresh = create_token(new_user.email, timedelta(days=7), "refresh")
    
   
  response.set_cookie(key="access_token", value=token, httponly=True, secure=False, samesite="lax", max_age=600)
  response.set_cookie(key="refresh_token", value=refresh, httponly=True, secure=False, samesite="lax", max_age=7*24*3600)
  
  return {"message" : "Account Created Successfully",
          "access_token": token, 
          "token_type": "Bearer"}

@router.post("/login", response_model=Token)
async def login(user_data : Login_User, db : db_dependency, response: Response):
  user = authenticate_user(user_data.email, user_data.password, db)
  
  if user is None:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Credentials")
  
  token = create_token(user.email, timedelta(minutes=10), "access")
  refresh = create_token(user.email, timedelta(days=7), "refresh")
   
  response.set_cookie(key="access_token", value=token, httponly=True, secure=False, samesite="lax", max_age=600)
  response.set_cookie(key="refresh_token", value=refresh, httponly=True, secure=False, samesite="lax", max_age=7*24*3600)
  
  return {"access_token" : token,
          "token_type" : "Bearer"}

@router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: db_dependency):
    refresh_token = request.cookies.get("refresh_token")
    
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")
        
    try:
        payload = jwt.decode(refresh_token, secret_key, algorithms=[algorithm])
        email = payload.get('sub')
        token_type = payload.get('type')
        
        if token_type != 'refresh':
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
            
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has expired. Please log in again.")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        
    # Verify the user still exists in the database
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    # Issue a new access token
    new_access_token = create_token(user.email, timedelta(minutes=10), "access")
    
    # Update the access token cookie
    response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=False, samesite="lax", max_age=600)
    
    return {"message": "Token refreshed successfully", 
            "access_token": new_access_token, 
            "token_type": "Bearer"}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", httponly=True, secure=False, samesite="lax")
    response.delete_cookie(key="refresh_token", httponly=True, secure=False, samesite="lax")
    return {"message": "Logged out successfully"}

@router.get("/me")
async def user(current_user: Annotated[User, Depends(get_current_user)]):
    return {"username": current_user.username}

@router.delete("/delete-account") 
async def delete(
    current_user: Annotated[User, Depends(get_current_user)], 
    db: db_dependency,
    response: Response 
):
    db.delete(current_user)
    db.commit()
    
    # 2. Modify the injected response directly
    response.delete_cookie(key="access_token", httponly=True, secure=False, samesite="lax")
    response.delete_cookie(key="refresh_token", httponly=True, secure=False, samesite="lax")
    
    return {"message": "Account Deleted successfully"}