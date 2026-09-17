"""Public booking blueprint — members choose a location and reserve a seat/room."""
from __future__ import annotations

from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user, login_required

from ...models import Location, Seat, ConferenceRoom, SeatType, RoomWaitlist, WaitlistStatus, RecurringRoomBooking, RecurrencePattern
from ...services.booking_service import (
    create_seat_booking, create_room_booking, quote_seat, quote_room,
    BookingError, check_seat_conflict, check_room_conflict,
)
from ...services.formatting import format_money, now_local, parse_local_naive_to_utc
from ...utils.decorators import member_required

booking_bp = Blueprint("book", __name__, template_folder="../../templates")


@booking_bp.route("/")
@login_required
def index():
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    return render_template("booking/locations.html", locations=locations)


@booking_bp.route("/locations/<int:location_id>")
@login_required
def location_home(location_id: int):
    loc = Location.query.get_or_404(location_id)
    hot_desks = [s for s in loc.seats if s.seat_type == SeatType.HOT_DESK and s.is_active]
    rooms = [r for r in loc.rooms if r.is_active]
    return render_template("booking/location_home.html",
                           location=loc, hot_desks=hot_desks, rooms=rooms)


# ---------------------------------------------------------------- seats --

@booking_bp.route("/seats/<int:seat_id>", methods=["GET", "POST"])
@member_required
def seat_book(seat_id: int):
    seat = Seat.query.get_or_404(seat_id)

    default_start = (now_local() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    default_end = default_start + timedelta(hours=4)

    ctx = {"seat": seat, "quote": None, "error": None,
           "start": default_start.strftime("%Y-%m-%dT%H:%M"),
           "end": default_end.strftime("%Y-%m-%dT%H:%M")}

    if request.method == "POST":
        action = request.form.get("action", "quote")
        try:
            start = parse_local_naive_to_utc(request.form["start"])
            end = parse_local_naive_to_utc(request.form["end"])
        except (KeyError, ValueError):
            flash("Invalid start or end time.", "danger")
            return render_template("booking/seat_book.html", **ctx)

        ctx["start"] = request.form["start"]
        ctx["end"] = request.form["end"]

        if action == "book":
            try:
                b = create_seat_booking(user=current_user, seat=seat, start=start, end=end,
                                        notes=request.form.get("notes"))
                flash(f"Seat booked. Total {format_money(b.total_amount)}.", "success")
                return redirect(url_for("member.bookings"))
            except BookingError as e:
                ctx["error"] = str(e)

        # Always show a quote
        if end > start:
            ctx["quote"] = quote_seat(seat, start, end)
            ctx["has_conflict"] = check_seat_conflict(seat.id, start, end, booker=current_user)

    return render_template("booking/seat_book.html", **ctx)


# ----------------------------------------------------- conference rooms --

@booking_bp.route("/rooms/<int:room_id>", methods=["GET", "POST"])
@member_required
def room_book(room_id: int):
    room = ConferenceRoom.query.get_or_404(room_id)

    default_start = (now_local() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0, tzinfo=None)
    default_end = default_start + timedelta(hours=1)

    ctx = {"room": room, "quote": None, "error": None,
           "start": default_start.strftime("%Y-%m-%dT%H:%M"),
           "end": default_end.strftime("%Y-%m-%dT%H:%M")}

    if request.method == "POST":
        action = request.form.get("action", "quote")
        try:
            start = parse_local_naive_to_utc(request.form["start"])
            end = parse_local_naive_to_utc(request.form["end"])
        except (KeyError, ValueError):
            flash("Invalid start or end time.", "danger")
            return render_template("booking/room_book.html", **ctx)

        ctx["start"] = request.form["start"]
        ctx["end"] = request.form["end"]
        attendees = int(request.form.get("attendees", 1))
        title = request.form.get("title")
        notes = request.form.get("notes")

        if action == "book":
            try:
                b = create_room_booking(user=current_user, room=room, start=start, end=end,
                                        title=title, attendees=attendees, notes=notes)
                msg = f"Room booked. "
                if b.credits_used:
                    msg += f"Used {b.credits_used} credit(s). "
                if b.total_amount and b.total_amount > 0:
                    msg += f"Charge {format_money(b.total_amount)}."
                flash(msg, "success")
                return redirect(url_for("member.bookings"))
            except BookingError as e:
                ctx["error"] = str(e)

        if end > start:
            ctx["quote"] = quote_room(current_user, room, start, end)
            ctx["has_conflict"] = check_room_conflict(room.id, start, end)

    return render_template("booking/room_book.html", **ctx)


# --------- waitlist + recurring room bookings ----------

@booking_bp.route("/rooms/<int:room_id>/waitlist", methods=["POST"])
@member_required
def room_waitlist_join(room_id: int):
    from flask import g
    room = ConferenceRoom.query.get_or_404(room_id)
    try:
        start = parse_local_naive_to_utc(request.form["start"])
        end = parse_local_naive_to_utc(request.form["end"])
    except (KeyError, ValueError):
        flash("Invalid slot.", "warning")
        return redirect(url_for("book.room_book", room_id=room_id))
    from ...extensions import db as _db
    entry = RoomWaitlist(
        tenant_id=getattr(g, "tenant_id", None),
        room_id=room.id, user_id=current_user.id,
        start_at=start, end_at=end, status=WaitlistStatus.WAITING,
    )
    _db.session.add(entry); _db.session.commit()
    flash("You've been added to the waitlist. We'll email you if a slot opens up.", "info")
    return redirect(url_for("member.dashboard"))


@booking_bp.route("/rooms/<int:room_id>/recurring", methods=["POST"])
@member_required
def room_recurring_create(room_id: int):
    from flask import g
    from datetime import date as _date, time as _time
    room = ConferenceRoom.query.get_or_404(room_id)
    try:
        pattern = RecurrencePattern(request.form.get("pattern", "weekly"))
        start_time = _time.fromisoformat(request.form["start_time"])
        end_time = _time.fromisoformat(request.form["end_time"])
        start_date = _date.fromisoformat(request.form["start_date"])
        end_date = _date.fromisoformat(request.form["end_date"])
    except (KeyError, ValueError):
        flash("Invalid recurring request.", "warning")
        return redirect(url_for("book.room_book", room_id=room_id))
    from ...extensions import db as _db
    rec = RecurringRoomBooking(
        tenant_id=getattr(g, "tenant_id", None),
        room_id=room.id, user_id=current_user.id,
        pattern=pattern, start_time=start_time, end_time=end_time,
        start_date=start_date, end_date=end_date, is_active=True,
    )
    _db.session.add(rec); _db.session.commit()
    flash("Recurring booking series saved. Individual slots will be created nightly.", "success")
    return redirect(url_for("member.dashboard"))
