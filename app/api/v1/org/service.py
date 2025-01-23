from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from models.org import Org
from .schema import OrgCreate, OrgUpdate
from utils.auth import get_password_hash, verify_password
from .repository import OrgRepository

def create_org(db: Session, org_data: OrgCreate) -> Org:
    repository = OrgRepository(db)
    if repository.get_by_email(org_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    hashed_password = get_password_hash(org_data.password)
    org = Org(
        email=org_data.email,
        name=org_data.name,
        password=hashed_password
    )
    return repository.create(org)

def get_org(db: Session, org_id: int) -> Org:
    repository = OrgRepository(db)
    org = repository.get_by_id(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    return org

def get_orgs(db: Session, skip: int = 0, limit: int = 100) -> list[Org]:
    repository = OrgRepository(db)
    return repository.get_all(skip, limit)

def update_org(db: Session, org_id: int, org_update: OrgUpdate) -> Org:
    repository = OrgRepository(db)
    org = get_org(db, org_id)
    
    update_data = org_update.dict(exclude_unset=True)
    if "password" in update_data:
        update_data["password"] = get_password_hash(update_data["password"])
    
    for key, value in update_data.items():
        setattr(org, key, value)
    
    return repository.update(org)

def delete_org(db: Session, org_id: int) -> dict:
    repository = OrgRepository(db)
    org = get_org(db, org_id)
    repository.delete(org)
    return {"message": "Organization deleted successfully"}

def authenticate_org(db: Session, email: str, password: str) -> Org | bool:
    repository = OrgRepository(db)
    org = repository.get_by_email(email)
    if not org:
        return False
    if not verify_password(password, org.password):
        return False
    return org
    
    