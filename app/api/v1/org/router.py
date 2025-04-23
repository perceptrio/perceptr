from typing import List

from api.v1.org import service
from api.v1.org.schema import OrgCreate, OrgLogin, OrgResponse, OrgUpdate, Token
from common.middleware import GetPayload, get_current_org
from common.types import CreateTokenPayload, TokenPayload
from core.constants import APIPath
from database import get_db
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing_extensions import Annotated
from utils.auth import create_access_token, create_refresh_token

router = APIRouter(prefix=f"{APIPath.V1}/orgs", tags=["organizations"])


@router.post("/signup", response_model=Token)
def signup(org: OrgCreate, db: Session = Depends(get_db)):
    """Create a new organization account"""
    org = service.create_org(db=db, org_data=org)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to create organization",
        )
    access_token = create_access_token(data=CreateTokenPayload(org_id=org.id))
    refresh_token = create_refresh_token(data=CreateTokenPayload(org_id=org.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/login", response_model=Token)
async def login(credentials: OrgLogin, db: Session = Depends(get_db)):
    """Login with email and password to get access token"""
    org = service.authenticate_org(db, credentials.email, credentials.password)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data=CreateTokenPayload(org_id=org.id))
    refresh_token = create_refresh_token(data=CreateTokenPayload(org_id=org.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# Keep the /token endpoint for OAuth2 compatibility
@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """OAuth2 compatible token login, get an access token for future requests"""
    org = service.authenticate_org(db, form_data.username, form_data.password)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data=CreateTokenPayload(org_id=org.id))
    refresh_token = create_refresh_token(data=CreateTokenPayload(org_id=org.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/refresh", response_model=Token)
async def refresh_token(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="refresh"))],
):
    return {
        "access_token": create_access_token(CreateTokenPayload(org_id=payload.org.id)),
        "refresh_token": create_refresh_token(
            CreateTokenPayload(org_id=payload.org.id)
        ),
        "token_type": "bearer",
    }


@router.get("/me", response_model=OrgResponse)
async def read_orgs_me(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    return service.get_org(db=db, org_id=payload.org.id)


# TODO: Add admin middleware
# @router.get("/{org_id}", response_model=OrgResponse)
# def get_org(org_id: int, db: Session = Depends(get_db)):
#     return service.get_org(db=db, org_id=org_id)

# @router.get("/", response_model=List[OrgResponse])
# def get_orgs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
#     return service.get_orgs(db=db, skip=skip, limit=limit)

# @router.put("/{org_id}", response_model=OrgResponse)
# def update_org(
#     org_id: int,
#     org_update: OrgUpdate,
#     db: Session = Depends(get_db),
#     current_org: OrgResponse = Depends(get_current_org)
# ):
#     if current_org.id != org_id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Not authorized to update this organization"
#         )
#     return service.update_org(db=db, org_id=org_id, org_update=org_update)

# @router.delete("/{org_id}")
# def delete_org(
#     org_id: int,
#     db: Session = Depends(get_db),
#     current_org: OrgResponse = Depends(get_current_org)
# ):
#     if current_org.id != org_id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Not authorized to delete this organization"
#         )
#     return service.delete_org(db=db, org_id=org_id)
