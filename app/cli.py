"""Flask CLI commands: create super admin & seed demo data."""
from __future__ import annotations

from datetime import date, time
from decimal import Decimal

import click
from flask import Flask
from flask.cli import with_appcontext

from .extensions import db
from .models import (
    User, UserRole, Company, CompanyStatus,
    Location, Floor, Seat, SeatType, ConferenceRoom,
    PricingPlan, PlanType, BillingCycle, Subscription, SubscriptionStatus,
    Amenity, RoomAmenity,
)


def register_cli(app: Flask) -> None:
    app.cli.add_command(create_admin_cmd)
    app.cli.add_command(seed_demo_cmd)


@click.command("create-admin")
@click.option("--email", required=True)
@click.option("--password", required=True)
@click.option("--name", default="Platform Admin")
@with_appcontext
def create_admin_cmd(email: str, password: str, name: str) -> None:
    """Create a super admin user."""
    if User.query.filter_by(email=email).first():
        click.echo(f"User {email} already exists.")
        return
    u = User(email=email, full_name=name, role=UserRole.SUPER_ADMIN,
             is_active=True, email_verified=True)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.echo(f"Created super admin: {email}")


@click.command("seed-demo")
@with_appcontext
def seed_demo_cmd() -> None:
    """Populate database with sample locations, seats, rooms, plans, and users."""
    from flask import current_app

    # --- super admin ---
    email = current_app.config["BOOTSTRAP_ADMIN_EMAIL"]
    if not User.query.filter_by(email=email).first():
        admin = User(email=email, full_name="Platform Admin",
                     role=UserRole.SUPER_ADMIN, is_active=True, email_verified=True)
        admin.set_password(current_app.config["BOOTSTRAP_ADMIN_PASSWORD"])
        db.session.add(admin)
        click.echo(f"Seeded super admin: {email}")

    # --- CoWorkHub manager (day-to-day operations) ---
    manager_email = "manager@coworkhub.io"
    if not User.query.filter_by(email=manager_email).first():
        mgr = User(email=manager_email, full_name="Operations Manager",
                   role=UserRole.MANAGER, is_active=True, email_verified=True)
        mgr.set_password("ChangeMe123!")
        db.session.add(mgr)
        click.echo(f"Seeded manager: {manager_email}")

    # --- amenities ---
    amenity_names = ["Wi-Fi", "Coffee", "Printing", "Phone booths", "Kitchen", "Shower", "Bike storage"]
    for n in amenity_names:
        if not Amenity.query.filter_by(name=n).first():
            db.session.add(Amenity(name=n))

    room_amenity_names = ["TV Screen", "Whiteboard", "Video Conference", "Speakerphone"]
    for n in room_amenity_names:
        if not RoomAmenity.query.filter_by(name=n).first():
            db.session.add(RoomAmenity(name=n))

    db.session.flush()

    # --- location ---
    loc = Location.query.filter_by(code="NYC-01").first()
    if not loc:
        loc = Location(
            name="CoWorkHub NYC — Bryant Park", code="NYC-01",
            address_line1="1140 Avenue of the Americas",
            city="New York", state="NY", country="US", postal_code="10036",
            timezone="America/New_York",
            open_time=time(7, 0), close_time=time(22, 0),
            description="Flagship NYC location with 3 floors of workspace.",
        )
        db.session.add(loc)
        db.session.flush()

        # floors
        ground = Floor(location_id=loc.id, level=1, name="Ground — Lounge")
        l5 = Floor(location_id=loc.id, level=5, name="Level 5 — Hot Desks")
        l6 = Floor(location_id=loc.id, level=6, name="Level 6 — Dedicated Desks")
        l7 = Floor(location_id=loc.id, level=7, name="Level 7 — Private Offices")
        db.session.add_all([ground, l5, l6, l7])
        db.session.flush()

        # seats
        for i in range(1, 21):
            db.session.add(Seat(
                location_id=loc.id, floor_id=l5.id,
                code=f"L5-HD-{i:03d}", seat_type=SeatType.HOT_DESK,
                hourly_rate=Decimal("8.00"), daily_rate=Decimal("35.00"),
                monthly_rate=Decimal("299.00"),
            ))
        for i in range(1, 11):
            db.session.add(Seat(
                location_id=loc.id, floor_id=l6.id,
                code=f"L6-DD-{i:03d}", seat_type=SeatType.DEDICATED_DESK,
                monthly_rate=Decimal("599.00"),
            ))
        for i in range(1, 6):
            db.session.add(Seat(
                location_id=loc.id, floor_id=l7.id,
                code=f"L7-PO-{i:03d}", seat_type=SeatType.PRIVATE_OFFICE,
                capacity=4, monthly_rate=Decimal("2499.00"),
            ))

        # rooms
        db.session.add_all([
            ConferenceRoom(location_id=loc.id, floor_id=ground.id, code="G-BOARD",
                           name="The Boardroom", capacity=12,
                           hourly_rate=Decimal("60.00"), credit_cost_per_hour=2,
                           description="Boardroom with 65\" TV and speakerphone."),
            ConferenceRoom(location_id=loc.id, floor_id=l5.id, code="L5-HUD",
                           name="Hudson", capacity=6,
                           hourly_rate=Decimal("30.00"), credit_cost_per_hour=1,
                           description="6-person meeting room with whiteboard."),
            ConferenceRoom(location_id=loc.id, floor_id=l5.id, code="L5-CEN",
                           name="Central", capacity=4,
                           hourly_rate=Decimal("20.00"), credit_cost_per_hour=1),
            ConferenceRoom(location_id=loc.id, floor_id=l7.id, code="L7-EXEC",
                           name="Executive Suite", capacity=8,
                           hourly_rate=Decimal("45.00"), credit_cost_per_hour=2),
        ])
        click.echo(f"Seeded location {loc.code} with seats & rooms.")

    # --- pricing plans ---
    plans_seed = [
        ("Hot Desk Monthly", PlanType.HOT_DESK, BillingCycle.MONTHLY, Decimal("299"), 8, 1),
        ("Dedicated Desk", PlanType.DEDICATED_DESK, BillingCycle.MONTHLY, Decimal("599"), 20, 1),
        ("Private Office (4-person)", PlanType.PRIVATE_OFFICE, BillingCycle.MONTHLY, Decimal("2499"), 40, 1),
        ("All Access", PlanType.ALL_ACCESS, BillingCycle.MONTHLY, Decimal("499"), 12, 0),
        ("Day Pass", PlanType.DAY_PASS, BillingCycle.DAILY, Decimal("35"), 0, 1),
    ]
    for name, ptype, cycle, price, credits, max_loc in plans_seed:
        if not PricingPlan.query.filter_by(name=name).first():
            db.session.add(PricingPlan(
                name=name, plan_type=ptype, billing_cycle=cycle,
                base_price=price, included_meeting_credits=credits,
                max_locations=max_loc,
            ))

    # --- demo company ---
    if not Company.query.filter_by(name="Acme Robotics").first():
        acme = Company(
            name="Acme Robotics", legal_name="Acme Robotics Inc.",
            billing_email="billing@acme.example",
            industry="Hardware", status=CompanyStatus.ACTIVE,
            max_employees=25,
        )
        db.session.add(acme)
        db.session.flush()

        ca = User(email="jane@acme.example", full_name="Jane Doe",
                  role=UserRole.COMPANY_ADMIN, company_id=acme.id, is_active=True)
        ca.set_password("ChangeMe123!")
        emp = User(email="bob@acme.example", full_name="Bob Smith",
                   role=UserRole.EMPLOYEE, company_id=acme.id, is_active=True)
        emp.set_password("ChangeMe123!")
        db.session.add_all([ca, emp])

        # Assign a subscription
        plan = PricingPlan.query.filter_by(name="Dedicated Desk").first()
        if plan:
            db.session.add(Subscription(
                plan_id=plan.id, company_id=acme.id, quantity=5,
                unit_price=plan.base_price, start_date=date.today(),
                status=SubscriptionStatus.ACTIVE,
                meeting_credits_balance=plan.included_meeting_credits * 5,
            ))
        click.echo("Seeded demo company 'Acme Robotics' (jane@acme.example / ChangeMe123!)")

    # --- demo individual ---
    if not User.query.filter_by(email="alex@example.com").first():
        alex = User(email="alex@example.com", full_name="Alex Freelancer",
                    role=UserRole.INDIVIDUAL, is_active=True)
        alex.set_password("ChangeMe123!")
        db.session.add(alex)
        click.echo("Seeded individual member (alex@example.com / ChangeMe123!)")

    db.session.commit()
    click.echo("Done. Sign in at /auth/login")
