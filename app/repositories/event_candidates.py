from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EventCandidateModel


class EventCandidateRepository:
    """공연·티켓 이벤트 후보의 저장 및 필터 조회를 담당한다."""
    def __init__(self, session: Session):
        self.session = session

    def create(self, values: dict) -> EventCandidateModel:
        event = EventCandidateModel(**values)
        self.session.add(event)
        self.session.flush()
        return event

    def list(self, **filters: object) -> list[EventCandidateModel]:
        statement = select(EventCandidateModel)
        for field, value in filters.items():
            if value is not None:
                column = getattr(EventCandidateModel, field)
                statement = statement.where(column.in_(value) if isinstance(value, list) else column == value)
        return list(self.session.scalars(statement.order_by(EventCandidateModel.created_at.desc())))
