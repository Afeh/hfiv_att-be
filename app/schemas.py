from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── Attendance schemas ─────────────────────────────────────────────


class PersonBase(BaseModel):
    name: str


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    name: str


class Person(PersonBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class AttendanceCreate(BaseModel):
    person_id: int
    attendance_date: Optional[date] = None  # defaults to today if omitted
    is_absent: bool = False


class AttendanceRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    is_absent: bool
    person: Person


class PersonStats(BaseModel):
    name: str
    id: int
    total_possible: int
    total_attendance: int
    missed_attendance: int


class PinVerify(BaseModel):
    pin: str


# ── Contribution Tracker schemas ────────────────────────────────────

# -- Group Settings --
class GroupSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_name: str
    currency_symbol: str
    override_goal_amount: Optional[int] = None


class GroupSettingsUpdate(BaseModel):
    group_name: Optional[str] = None
    currency_symbol: Optional[str] = None
    override_goal_amount: Optional[int] = None


# -- Categories --
class CategoryCreate(BaseModel):
    name: str
    override_goal_amount: Optional[int] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    override_goal_amount: Optional[int] = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    override_goal_amount: Optional[int] = None


# -- Pledges --
class PledgeCreate(BaseModel):
    category_id: int
    person_name: str
    pledged_amount: Optional[int] = None
    pledged_item: Optional[str] = None
    is_in_kind: bool = False
    note: Optional[str] = None


class PledgeUpdate(BaseModel):
    person_name: Optional[str] = None
    pledged_amount: Optional[int] = None
    pledged_item: Optional[str] = None
    is_in_kind: Optional[bool] = None
    note: Optional[str] = None


class PledgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    person_name: str
    pledged_amount: Optional[int] = None
    pledged_item: Optional[str] = None
    is_in_kind: bool
    in_kind_fulfilled: bool
    note: Optional[str] = None
    total_contributed: int = 0
    balance: Optional[int] = None


# -- Contributions --
class ContributionCreate(BaseModel):
    amount: int
    date_paid: date
    note: Optional[str] = None


class ContributionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pledge_id: int
    amount: int
    date_paid: date
    note: Optional[str] = None


# -- Summary / Dashboard --
class CategorySummary(BaseModel):
    id: int
    name: str
    total_pledged: int
    total_contributed: int
    goal_amount: int
    pct_complete: float
    in_kind_total: int
    in_kind_fulfilled: int
    pledge_count: int


class TopContributor(BaseModel):
    person_name: str
    total_contributed: int


class OutstandingPledger(BaseModel):
    pledge_id: int
    person_name: str
    category_name: str
    pledged_amount: int
    total_contributed: int
    balance: int


class Summary(BaseModel):
    group_name: str
    currency_symbol: str
    total_pledged: int
    total_contributed: int
    goal_amount: int
    pct_complete: float
    categories: list[CategorySummary]
    top_contributors: list[TopContributor]
    outstanding_pledgers: list[OutstandingPledger]
    in_kind_total: int
    in_kind_fulfilled: int


# -- Quick Donate (walk-in donations) --
class QuickDonate(BaseModel):
    category_id: int
    person_name: str
    amount: int
    date_paid: date
    note: Optional[str] = None


class QuickDonateResponse(BaseModel):
    pledge: PledgeOut
    contribution: ContributionOut
