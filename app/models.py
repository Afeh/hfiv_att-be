from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from .database import Base


# ── Attendance models ─────────────────────────────────────────────

class Person(Base):
    __tablename__ = "people"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    attendance_records = relationship(
        "Attendance", back_populates="person", cascade="all, delete-orphan"
    )


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (UniqueConstraint("person_id", "date", name="uq_person_date"),)

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, ForeignKey("people.id"), nullable=False)
    date = Column(Date, nullable=False, index=True)
    is_absent = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    person = relationship("Person", back_populates="attendance_records")


# ── Contribution Tracker models ────────────────────────────────────

class ContributionGroup(Base):
    __tablename__ = "contribution_groups"

    id = Column(Integer, primary_key=True, index=True)
    group_name = Column(String, nullable=False, default="My Group")
    currency_symbol = Column(String, nullable=False, default="₦")
    override_goal_amount = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    categories = relationship(
        "ContributionCategory", back_populates="group", cascade="all, delete-orphan"
    )


class ContributionCategory(Base):
    __tablename__ = "contribution_categories"

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("contribution_groups.id"), nullable=False)
    name = Column(String, nullable=False)
    override_goal_amount = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("ContributionGroup", back_populates="categories")
    pledges = relationship(
        "Pledge", back_populates="category", cascade="all, delete-orphan"
    )


class Pledge(Base):
    __tablename__ = "pledges"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("contribution_categories.id"), nullable=False)
    person_name = Column(String, nullable=False)
    pledged_amount = Column(Integer, nullable=True)  # nullable for in-kind
    pledged_item = Column(String, nullable=True)  # description for in-kind
    is_in_kind = Column(Boolean, default=False, nullable=False)
    in_kind_fulfilled = Column(Boolean, default=False, nullable=False)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    category = relationship("ContributionCategory", back_populates="pledges")
    contributions = relationship(
        "Contribution", back_populates="pledge", cascade="all, delete-orphan"
    )


class Contribution(Base):
    __tablename__ = "contributions"

    id = Column(Integer, primary_key=True, index=True)
    pledge_id = Column(Integer, ForeignKey("pledges.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    date_paid = Column(Date, nullable=False)
    note = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    pledge = relationship("Pledge", back_populates="contributions")
