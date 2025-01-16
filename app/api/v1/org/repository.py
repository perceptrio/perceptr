from sqlalchemy.orm import Session
from models.org import Org

class OrgRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, org: Org) -> Org:
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)
        return org

    def get_by_id(self, org_id: int) -> Org | None:
        return self.db.query(Org).filter(Org.id == org_id).first()

    def get_by_email(self, email: str) -> Org | None:
        return self.db.query(Org).filter(Org.email == email).first()

    def get_all(self, skip: int = 0, limit: int = 100) -> list[Org]:
        return self.db.query(Org).offset(skip).limit(limit).all()

    def update(self, org: Org) -> Org:
        self.db.commit()
        self.db.refresh(org)
        return org

    def delete(self, org: Org) -> None:
        self.db.delete(org)
        self.db.commit()
