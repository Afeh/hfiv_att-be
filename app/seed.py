"""Seed script for the Contribution Tracker.

Usage:
    cd hfiv_att-be
    python -m app.seed

Creates a default group with "Seed" and "Dinner" categories plus sample pledges.
"""

from datetime import date

from .database import Base, engine, SessionLocal
from .models import ContributionGroup, ContributionCategory, Pledge, Contribution

# ── Seed Data ──────────────────────────────────────────────────────
# Format: (person_name, amount_or_None, item_or_None, is_in_kind, note_or_None)

SEED_PLEDGES = [
    ("Ajibola Victor", 2000, None, False, None),
    ("Melody", 5000, None, False, None),
    ("Temitope", 5000, None, False, None),
    ("Joy", 10000, None, False, None),
    ("Prisca", 3000, None, False, None),
    ("Peace", 5000, None, False, None),
    ("Feranmi", 2000, None, False, None),
    ("Bro Tobi", 10000, None, False, None),
    ("Pricilla", 2000, None, False, None),
    ("Victoria", 2000, None, False, None),
    ("Kelechi", 1000, None, False, None),
    ("Dorcas", 1000, None, False, None),
    ("Success", 2000, None, False, None),
    ("Taiwo Kehinde", 3000, None, False, None),
    ("Sis Bolanle", 5000, None, False, None),
    ("Gideon", 1000, None, False, None),
    ("Bro Miracle", 10000, None, False, None),
    ("Fayo", 5000, None, False, None),
    ("Emmanuel", 2000, None, False, None),
    ("Sis Chidimma", 10000, None, False, None),
    ("Bro Israel", 10000, None, False, None),
    ("Oyetunji Victor", 2000, None, False, None),
    ("Rev.", 10000, None, False, None),
]

DINNER_PLEDGES = [
    # Cash pledges with item notes
    ("Success", 3000, None, False, "flour"),
    ("Pricillia", 2000, None, False, "boom"),
    ("Kelechi", 2000, None, False, "boom"),
    ("Nifemi", 2000, None, False, "boom"),
    ("Dorcas", 2000, None, False, "boom"),
    ("Victoria", 2000, None, False, "boom"),
    ("Fayo", 2500, None, False, "seasoning/sugar"),
    ("Ajiboye Victor", 2000, None, False, "1 pack of bottle water"),
    ("Sis Bola", 3000, None, False, "2 packs of bottle water"),
    ("Prisca", 5000, None, False, "wine"),
    ("Emmanuel", 3000, None, False, "ponmon"),
    ("Taiwo Kehinde", 5000, None, False, "fruits"),
    ("Temitope", 5000, None, False, "groundnut oil"),
    # In-kind pledges (no cash amount)
    ("Gideon", None, "Ice block", True, None),
    ("Solomon", None, "1 pack of drinks", True, None),
    ("Joy", None, "Gizzard", True, None),
    ("Oyetunji Victor", None, "1 pack of drinks", True, None),
    ("Melody", None, "Gizzard", True, None),
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check if already seeded
        existing = db.query(ContributionGroup).first()
        if existing:
            print(f"⚠️  Database already has a group ({existing.group_name}). Skipping seed.")
            return

        # Create group
        group = ContributionGroup(
            group_name="My Group",
            currency_symbol="₦",
        )
        db.add(group)
        db.flush()

        # Create categories
        seed_cat = ContributionCategory(group_id=group.id, name="Seed")
        dinner_cat = ContributionCategory(group_id=group.id, name="Dinner")
        db.add(seed_cat)
        db.add(dinner_cat)
        db.flush()

        # Seed pledges for "Seed" category
        for person, amount, item, is_in_kind, note in SEED_PLEDGES:
            pledge = Pledge(
                category_id=seed_cat.id,
                person_name=person,
                pledged_amount=amount,
                pledged_item=item,
                is_in_kind=is_in_kind,
                note=note,
            )
            db.add(pledge)

        # Seed pledges for "Dinner" category
        for person, amount, item, is_in_kind, note in DINNER_PLEDGES:
            pledge = Pledge(
                category_id=dinner_cat.id,
                person_name=person,
                pledged_amount=amount,
                pledged_item=item,
                is_in_kind=is_in_kind,
                note=note,
            )
            db.add(pledge)

        db.commit()

        # Print summary
        seed_cash = sum(1 for _, a, _, ik, _ in SEED_PLEDGES if not ik and a)
        seed_total = sum(a for _, a, _, ik, _ in SEED_PLEDGES if not ik and a)
        dinner_cash = sum(1 for _, a, _, ik, _ in DINNER_PLEDGES if not ik and a)
        dinner_total = sum(a for _, a, _, ik, _ in DINNER_PLEDGES if not ik and a)
        dinner_inkind = sum(1 for _, _, _, ik, _ in DINNER_PLEDGES if ik)

        print("✅ Seed data created successfully!")
        print(f"   Group: {group.group_name}")
        print(f"   Seed: {len(SEED_PLEDGES)} pledges ({seed_cash} cash = ₦{seed_total:,})")
        print(f"   Dinner: {len(DINNER_PLEDGES)} pledges ({dinner_cash} cash = ₦{dinner_total:,}, {dinner_inkind} in-kind)")
    except Exception as e:
        db.rollback()
        print(f"❌ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
