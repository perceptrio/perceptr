# middleware
from typing import Annotated, Literal
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from requests import Session

from database import get_db
from models.org import Org
from utils.auth import ALGORITHM, SECRET_KEY, REFRESH_SECRET_KEY
from common.types import TokenPayload, AbstractOrg
from common.services.logger import logger

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token" )


class GetPayload:
    def __init__(self, type: Literal["access", "refresh"]):
        self.type = type
    
    async def __call__(self, token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
        credentials_exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="failed to authenticate, please login again",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            if self.type == "access":
                payload_dict = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            else:
                payload_dict = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError as e:
            logger.error(f"Error decoding token in middleware: {e}")
            raise credentials_exception
        org_id = payload_dict.get("org_id")
        try:
            org = db.query(Org).filter(Org.id == org_id).first()
            if org is None:
                raise credentials_exception
        except Exception as e:
            logger.error(f"Error getting org in middleware: {e}")
            raise credentials_exception
        payload = TokenPayload(
            org=AbstractOrg(
                id=org.id,
                name=org.name,
                email=org.email
            )
        )
        return payload
        
            
    

async def get_current_org(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Org:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        org_id = payload.get("org_id")
        if org_id is None:
            raise credentials_exception
        token_data = TokenPayload(org_id=org_id)
    except JWTError:
        raise credentials_exception
    
    org = db.query(Org).filter(Org.id == token_data.org_id).first()
    if org is None:
        raise credentials_exception
    return org 
