from datetime import date as date_type
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

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
    return query.order_by(models.Person.name).all()


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


# ═══════════════════════════════════════════════════════════════════
# Contribution Tracker endpoints
# ═══════════════════════════════════════════════════════════════════

def _get_or_create_group(db: Session) -> models.ContributionGroup:
    """Return the single group, creating a default one if needed."""
    group = db.query(models.ContributionGroup).first()
    if not group:
        group = models.ContributionGroup(group_name="My Group", currency_symbol="₦")
        db.add(group)
        db.commit()
        db.refresh(group)
    return group


# ── Settings ───────────────────────────────────────────────────────

@app.get("/ct/settings", response_model=schemas.GroupSettings)
def get_ct_settings(db: Session = Depends(get_db)):
    return _get_or_create_group(db)


@app.patch("/ct/settings", response_model=schemas.GroupSettings)
def update_ct_settings(body: schemas.GroupSettingsUpdate, db: Session = Depends(get_db)):
    group = _get_or_create_group(db)
    if body.group_name is not None:
        group.group_name = body.group_name.strip()
    if body.currency_symbol is not None:
        group.currency_symbol = body.currency_symbol.strip()
    if body.override_goal_amount is not None:
        group.override_goal_amount = body.override_goal_amount
    db.commit()
    db.refresh(group)
    return group


# ── Categories ─────────────────────────────────────────────────────

@app.get("/ct/categories", response_model=list[schemas.CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    group = _get_or_create_group(db)
    return (
        db.query(models.ContributionCategory)
        .filter(models.ContributionCategory.group_id == group.id)
        .order_by(models.ContributionCategory.name)
        .all()
    )


@app.post("/ct/categories", response_model=schemas.CategoryOut, status_code=201)
def create_category(body: schemas.CategoryCreate, db: Session = Depends(get_db)):
    group = _get_or_create_group(db)
    cat = models.ContributionCategory(
        group_id=group.id,
        name=body.name.strip(),
        override_goal_amount=body.override_goal_amount,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@app.patch("/ct/categories/{category_id}", response_model=schemas.CategoryOut)
def update_category(category_id: int, body: schemas.CategoryUpdate, db: Session = Depends(get_db)):
    cat = db.get(models.ContributionCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    if body.name is not None:
        cat.name = body.name.strip()
    if body.override_goal_amount is not None:
        cat.override_goal_amount = body.override_goal_amount
    db.commit()
    db.refresh(cat)
    return cat


@app.delete("/ct/categories/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    cat = db.get(models.ContributionCategory, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(cat)
    db.commit()


# ── Pledges ────────────────────────────────────────────────────────

@app.get("/ct/pledges", response_model=list[schemas.PledgeOut])
def list_pledges(
    category_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(models.Pledge).options(
        joinedload(models.Pledge.contributions)
    )
    if category_id is not None:
        query = query.filter(models.Pledge.category_id == category_id)
    pledges = query.order_by(models.Pledge.person_name).all()

    result = []
    for p in pledges:
        total_contributed = sum(c.amount for c in p.contributions)
        balance = (p.pledged_amount - total_contributed) if p.pledged_amount else None
        result.append(
            schemas.PledgeOut(
                id=p.id,
                category_id=p.category_id,
                person_name=p.person_name,
                pledged_amount=p.pledged_amount,
                pledged_item=p.pledged_item,
                is_in_kind=p.is_in_kind,
                in_kind_fulfilled=p.in_kind_fulfilled,
                note=p.note,
                total_contributed=total_contributed,
                balance=balance,
            )
        )
    return result


@app.post("/ct/pledges", response_model=schemas.PledgeOut, status_code=201)
def create_pledge(body: schemas.PledgeCreate, db: Session = Depends(get_db)):
    # Validate category exists
    cat = db.get(models.ContributionCategory, body.category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    pledge = models.Pledge(
        category_id=body.category_id,
        person_name=body.person_name.strip(),
        pledged_amount=body.pledged_amount,
        pledged_item=body.pledged_item,
        is_in_kind=body.is_in_kind,
        note=body.note,
    )
    db.add(pledge)
    db.commit()
    db.refresh(pledge)
    return schemas.PledgeOut(
        id=pledge.id,
        category_id=pledge.category_id,
        person_name=pledge.person_name,
        pledged_amount=pledge.pledged_amount,
        pledged_item=pledge.pledged_item,
        is_in_kind=pledge.is_in_kind,
        in_kind_fulfilled=pledge.in_kind_fulfilled,
        note=pledge.note,
        total_contributed=0,
        balance=pledge.pledged_amount,
    )


@app.patch("/ct/pledges/{pledge_id}", response_model=schemas.PledgeOut)
def update_pledge(pledge_id: int, body: schemas.PledgeUpdate, db: Session = Depends(get_db)):
    pledge = db.get(models.Pledge, pledge_id)
    if not pledge:
        raise HTTPException(status_code=404, detail="Pledge not found")
    if body.person_name is not None:
        pledge.person_name = body.person_name.strip()
    if body.pledged_amount is not None:
        pledge.pledged_amount = body.pledged_amount
    if body.pledged_item is not None:
        pledge.pledged_item = body.pledged_item
    if body.is_in_kind is not None:
        pledge.is_in_kind = body.is_in_kind
    if body.note is not None:
        pledge.note = body.note
    db.commit()
    db.refresh(pledge)

    total_contributed = sum(c.amount for c in pledge.contributions)
    balance = (pledge.pledged_amount - total_contributed) if pledge.pledged_amount else None
    return schemas.PledgeOut(
        id=pledge.id,
        category_id=pledge.category_id,
        person_name=pledge.person_name,
        pledged_amount=pledge.pledged_amount,
        pledged_item=pledge.pledged_item,
        is_in_kind=pledge.is_in_kind,
        in_kind_fulfilled=pledge.in_kind_fulfilled,
        note=pledge.note,
        total_contributed=total_contributed,
        balance=balance,
    )


@app.delete("/ct/pledges/{pledge_id}", status_code=204)
def delete_pledge(pledge_id: int, db: Session = Depends(get_db)):
    pledge = db.get(models.Pledge, pledge_id)
    if not pledge:
        raise HTTPException(status_code=404, detail="Pledge not found")
    db.delete(pledge)
    db.commit()


@app.patch("/ct/pledges/{pledge_id}/fulfill", response_model=schemas.PledgeOut)
def fulfill_in_kind(pledge_id: int, db: Session = Depends(get_db)):
    """Toggle in-kind fulfillment on a pledge."""
    pledge = db.get(models.Pledge, pledge_id)
    if not pledge:
        raise HTTPException(status_code=404, detail="Pledge not found")
    pledge.in_kind_fulfilled = not pledge.in_kind_fulfilled
    db.commit()
    db.refresh(pledge)
    total_contributed = sum(c.amount for c in pledge.contributions)
    balance = (pledge.pledged_amount - total_contributed) if pledge.pledged_amount else None
    return schemas.PledgeOut(
        id=pledge.id,
        category_id=pledge.category_id,
        person_name=pledge.person_name,
        pledged_amount=pledge.pledged_amount,
        pledged_item=pledge.pledged_item,
        is_in_kind=pledge.is_in_kind,
        in_kind_fulfilled=pledge.in_kind_fulfilled,
        note=pledge.note,
        total_contributed=total_contributed,
        balance=balance,
    )


# ── Contributions ──────────────────────────────────────────────────

@app.post("/ct/pledges/{pledge_id}/contributions", response_model=schemas.ContributionOut, status_code=201)
def add_contribution(
    pledge_id: int, body: schemas.ContributionCreate, db: Session = Depends(get_db)
):
    pledge = db.get(models.Pledge, pledge_id)
    if not pledge:
        raise HTTPException(status_code=404, detail="Pledge not found")
    if not pledge.pledged_amount:
        raise HTTPException(status_code=400, detail="Cannot add cash contribution to an in-kind pledge")

    contribution = models.Contribution(
        pledge_id=pledge_id,
        amount=body.amount,
        date_paid=body.date_paid,
        note=body.note,
    )
    db.add(contribution)
    db.commit()
    db.refresh(contribution)
    return contribution


@app.delete("/ct/contributions/{contribution_id}", status_code=204)
def delete_contribution(contribution_id: int, db: Session = Depends(get_db)):
    contribution = db.get(models.Contribution, contribution_id)
    if not contribution:
        raise HTTPException(status_code=404, detail="Contribution not found")
    db.delete(contribution)
    db.commit()


@app.post("/ct/quick-donate", response_model=schemas.QuickDonateResponse, status_code=201)
def quick_donate(body: schemas.QuickDonate, db: Session = Depends(get_db)):
    """Create a pledge and first contribution in one step for walk-in donations."""
    cat = db.get(models.ContributionCategory, body.category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Create the pledge
    pledge = models.Pledge(
        category_id=body.category_id,
        person_name=body.person_name.strip(),
        pledged_amount=body.amount,
        is_in_kind=False,
    )
    db.add(pledge)
    db.flush()  # get the pledge id

    # Create the contribution
    contribution = models.Contribution(
        pledge_id=pledge.id,
        amount=body.amount,
        date_paid=body.date_paid,
        note=body.note,
    )
    db.add(contribution)
    db.commit()
    db.refresh(pledge)
    db.refresh(contribution)

    return schemas.QuickDonateResponse(
        pledge=schemas.PledgeOut(
            id=pledge.id,
            category_id=pledge.category_id,
            person_name=pledge.person_name,
            pledged_amount=pledge.pledged_amount,
            pledged_item=pledge.pledged_item,
            is_in_kind=pledge.is_in_kind,
            in_kind_fulfilled=pledge.in_kind_fulfilled,
            note=pledge.note,
            total_contributed=contribution.amount,
            balance=pledge.pledged_amount - contribution.amount,
        ),
        contribution=schemas.ContributionOut.model_validate(contribution),
    )


# ── Summary (Dashboard) ────────────────────────────────────────────

@app.get("/ct/summary", response_model=schemas.Summary)
def get_summary(db: Session = Depends(get_db)):
    group = _get_or_create_group(db)

    categories = (
        db.query(models.ContributionCategory)
        .filter(models.ContributionCategory.group_id == group.id)
        .order_by(models.ContributionCategory.name)
        .all()
    )

    total_pledged = 0
    total_contributed = 0
    in_kind_total = 0
    in_kind_fulfilled = 0
    category_summaries: list[schemas.CategorySummary] = []
    outstanding_map: dict[int, schemas.OutstandingPledger] = {}  # pledge_id -> outstanding
    contributor_totals: dict[str, int] = {}  # person_name -> total contributed

    for cat in categories:
        pledges = (
            db.query(models.Pledge)
            .options(joinedload(models.Pledge.contributions))
            .filter(models.Pledge.category_id == cat.id)
            .all()
        )

        cat_pledged = 0
        cat_contributed = 0
        cat_in_kind = 0
        cat_in_kind_fulfilled = 0

        for p in pledges:
            if p.is_in_kind:
                cat_in_kind += 1
                if p.in_kind_fulfilled:
                    cat_in_kind_fulfilled += 1
            else:
                p_amount = p.pledged_amount or 0
                p_contributed = sum(c.amount for c in p.contributions)
                cat_pledged += p_amount
                cat_contributed += p_contributed
                balance = p_amount - p_contributed
                if balance > 0:
                    outstanding_map[p.id] = schemas.OutstandingPledger(
                        pledge_id=p.id,
                        person_name=p.person_name,
                        category_name=cat.name,
                        pledged_amount=p_amount,
                        total_contributed=p_contributed,
                        balance=balance,
                    )
                # Track contributor totals
                if p_contributed > 0:
                    contributor_totals[p.person_name] = (
                        contributor_totals.get(p.person_name, 0) + p_contributed
                    )

        total_pledged += cat_pledged
        total_contributed += cat_contributed
        in_kind_total += cat_in_kind
        in_kind_fulfilled += cat_in_kind_fulfilled

        cat_goal = cat.override_goal_amount or cat_pledged
        cat_pct = (cat_contributed / cat_goal * 100) if cat_goal > 0 else 0.0

        category_summaries.append(
            schemas.CategorySummary(
                id=cat.id,
                name=cat.name,
                total_pledged=cat_pledged,
                total_contributed=cat_contributed,
                goal_amount=cat_goal,
                pct_complete=round(cat_pct, 1),
                in_kind_total=cat_in_kind,
                in_kind_fulfilled=cat_in_kind_fulfilled,
                pledge_count=len(pledges),
            )
        )

    group_goal = group.override_goal_amount or total_pledged
    group_pct = (total_contributed / group_goal * 100) if group_goal > 0 else 0.0

    # Top contributors (sorted by total contributed, desc)
    top_contributors = sorted(
        [
            schemas.TopContributor(person_name=name, total_contributed=amount)
            for name, amount in contributor_totals.items()
        ],
        key=lambda x: x.total_contributed,
        reverse=True,
    )[:10]

    # Outstanding pledgers (sorted by balance owed, desc)
    outstanding_pledgers = sorted(
        list(outstanding_map.values()),
        key=lambda x: x.balance,
        reverse=True,
    )

    return schemas.Summary(
        group_name=group.group_name,
        currency_symbol=group.currency_symbol,
        total_pledged=total_pledged,
        total_contributed=total_contributed,
        goal_amount=group_goal,
        pct_complete=round(group_pct, 1),
        categories=category_summaries,
        top_contributors=top_contributors,
        outstanding_pledgers=outstanding_pledgers,
        in_kind_total=in_kind_total,
        in_kind_fulfilled=in_kind_fulfilled,
    )
