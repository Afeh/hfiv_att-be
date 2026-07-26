from datetime import date as date_type
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models, schemas
from .database import Base, engine, get_db
from .settings import settings

Base.metadata.create_all(bind=engine)

# ── Migration: add is_absent column if missing (PostgreSQL & SQLite compatible) ─
with engine.connect() as conn:
    dialect = conn.dialect.name
    try:
        if dialect == "postgresql":
            conn.execute(
                text(
                    "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS is_absent "
                    "BOOLEAN NOT NULL DEFAULT false"
                )
            )
        else:
            conn.execute(
                text(
                    "ALTER TABLE attendance ADD COLUMN is_absent BOOLEAN NOT NULL DEFAULT 0"
                )
            )
        conn.commit()
    except Exception:
        pass  # column already exists

app = FastAPI(title=settings.app_title)

allowed_origins = [
    origin.strip()
    for origin in settings.allowed_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/people", response_model=list[schemas.Person])
def search_people(search: str = "", db: Session = Depends(get_db)):
    query = db.query(models.Person)
    if search:
        query = query.filter(func.lower(models.Person.name).contains(search.lower()))
    return query.order_by(models.Person.name).limit(20).all()


@app.post("/people", response_model=schemas.Person, status_code=201)
def create_person(person: schemas.PersonCreate, db: Session = Depends(get_db)):
    db_person = models.Person(name=person.name.strip())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person


@app.patch("/people/{person_id}", response_model=schemas.Person)
def update_person(person_id: int, body: schemas.PersonUpdate, db: Session = Depends(get_db)):
    db_person = db.get(models.Person, person_id)
    if not db_person:
        raise HTTPException(status_code=404, detail="Person not found")
    db_person.name = body.name.strip()
    db.commit()
    db.refresh(db_person)
    return db_person


@app.get("/attendance", response_model=list[schemas.AttendanceRecord])
def get_attendance(
    date: Optional[date_type] = Query(default=None),
    db: Session = Depends(get_db),
):
    target_date = date or date_type.today()
    return (
        db.query(models.Attendance)
        .join(models.Person)
        .filter(models.Attendance.date == target_date)
        .order_by(models.Person.name)
        .all()
    )


@app.post("/attendance", response_model=schemas.AttendanceRecord, status_code=201)
def mark_attendance(record: schemas.AttendanceCreate, db: Session = Depends(get_db)):
    person = db.get(models.Person, record.person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    attendance_date = record.attendance_date or date_type.today()

    # Upsert: if a record already exists for this (person_id, date), update it
    existing = (
        db.query(models.Attendance)
        .filter(
            models.Attendance.person_id == record.person_id,
            models.Attendance.date == attendance_date,
        )
        .first()
    )
    if existing:
        existing.is_absent = record.is_absent
        db.commit()
        db.refresh(existing)
        return existing

    db_record = models.Attendance(
        person_id=record.person_id,
        date=attendance_date,
        is_absent=record.is_absent,
    )
    db.add(db_record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Already marked present for this date"
        )
    db.refresh(db_record)
    return db_record


@app.post("/auth/verify-pin")
def verify_pin(body: schemas.PinVerify):
    if body.pin == settings.app_pin:
        return {"ok": True}
    raise HTTPException(status_code=401, detail="Invalid PIN")


@app.get("/people/stats", response_model=list[schemas.PersonStats])
def get_people_stats(db: Session = Depends(get_db)):
    # get all distinct attendance dates, ordered
    distinct_dates = [
        r[0] for r in db.query(models.Attendance.date).distinct().order_by(models.Attendance.date).all()
    ]

    people = db.query(models.Person).order_by(models.Person.name).all()

    # collect attendance records per person (date, is_absent)
    person_records: dict[int, list[tuple[date_type, bool]]] = {}
    for pid, adate, is_abs in db.query(
        models.Attendance.person_id,
        models.Attendance.date,
        models.Attendance.is_absent,
    ).all():
        person_records.setdefault(pid, []).append((adate, is_abs))

    result = []
    for p in people:
        person_joined = p.created_at.date()
        records = person_records.get(p.id, [])
        present_dates = {d for d, a in records if not a}
        absent_dates = {d for d, a in records if a}

        total_possible = sum(
            1 for d in distinct_dates
            if d >= person_joined or d in present_dates or d in absent_dates
        )
        present_count = len(present_dates)

        result.append(
            schemas.PersonStats(
                id=p.id,
                name=p.name,
                total_possible=total_possible,
                total_attendance=present_count,
                missed_attendance=total_possible - present_count,
            )
        )

    return result


@app.patch("/attendance/{attendance_id}/toggle", response_model=schemas.AttendanceRecord)
def toggle_attendance(attendance_id: int, db: Session = Depends(get_db)):
    """Toggle is_absent on an attendance record."""
    record = db.get(models.Attendance, attendance_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    record.is_absent = not record.is_absent
    db.commit()
    db.refresh(record)
    return record


@app.delete("/attendance/{attendance_id}", status_code=204)
def delete_attendance(attendance_id: int, db: Session = Depends(get_db)):
    record = db.get(models.Attendance, attendance_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(record)
    db.commit()


@app.delete("/data/reset", status_code=200)
def reset_database(db: Session = Depends(get_db)):
    """Delete all attendance records and people. Use this to start fresh."""
    db.query(models.Attendance).delete()
    db.query(models.Person).delete()
    db.commit()
    return {"ok": True, "message": "All records cleared."}
