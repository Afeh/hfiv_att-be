from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


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
