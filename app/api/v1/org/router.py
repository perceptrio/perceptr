from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List
from common.types import TokenPayload  
from typing_extensions import Annotated
from common.middleware import GetPayload, get_current_org

from database import get_db
from api.v1.org import service as org_service
from schemas.org_schema import OrgCreate, OrgResponse, OrgUpdate, OrgLogin, Token
from utils.auth import create_access_token, create_refresh_token
from core.constants import APIPath

router = APIRouter(prefix=f"{APIPath.V1}/orgs", tags=["organizations"])

@router.post("/signup", response_model=OrgResponse)
def signup(org: OrgCreate, db: Session = Depends(get_db)):
    """Create a new organization account"""
    return org_service.create_org(db=db, org_data=org)

@router.post("/login", response_model=Token)
async def login(
    credentials: OrgLogin,
    db: Session = Depends(get_db)
):
    """Login with email and password to get access token"""
    org = org_service.authenticate_org(db, credentials.email, credentials.password)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data=TokenPayload(org_id=str(org.id))
    )
    refresh_token = create_refresh_token(
        data=TokenPayload(org_id=str(org.id))
    )
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

# Keep the /token endpoint for OAuth2 compatibility
@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """OAuth2 compatible token login, get an access token for future requests"""
    org = org_service.authenticate_org(db, form_data.username, form_data.password)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data=TokenPayload(org_id=str(org.id))
    )
    refresh_token = create_refresh_token(
        data=TokenPayload(org_id=str(org.id))
    )
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/refresh", response_model=Token)
async def refresh_token(payload: Annotated[TokenPayload, Depends(GetPayload(type="refresh"))]):
    return {"access_token": create_access_token(payload), "refresh_token": create_refresh_token(payload), "token_type": "bearer"}

@router.get("/me", response_model=OrgResponse)
async def read_orgs_me(payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))], db: Session = Depends(get_db)):
    return org_service.get_org(db=db, org_id=payload.org_id)

# TODO: Add admin middleware
@router.get("/{org_id}", response_model=OrgResponse)
def get_org(org_id: int, db: Session = Depends(get_db)):
    return org_service.get_org(db=db, org_id=org_id)

@router.get("/", response_model=List[OrgResponse])
def get_orgs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return org_service.get_orgs(db=db, skip=skip, limit=limit)

@router.put("/{org_id}", response_model=OrgResponse)
def update_org(
    org_id: int,
    org_update: OrgUpdate,
    db: Session = Depends(get_db),
    current_org: OrgResponse = Depends(get_current_org)
):
    if current_org.id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this organization"
        )
    return org_service.update_org(db=db, org_id=org_id, org_update=org_update)

@router.delete("/{org_id}")
def delete_org(
    org_id: int,
    db: Session = Depends(get_db),
    current_org: OrgResponse = Depends(get_current_org)
):
    if current_org.id != org_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this organization"
        )
    return org_service.delete_org(db=db, org_id=org_id)
