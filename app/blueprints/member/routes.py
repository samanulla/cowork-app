"""Member portal (employees & individual users)."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import current_user, login_required

from ...extensions import db
from ...models import (
    SeatBooking, RoomBooking, BookingStatus, Invoice, Subscription, SubscriptionStatus,
)
from ...services.booking_service import cancel_booking, BookingError
from ...utils.decorators import member_required

member_bp = Blueprint("member", __name__, template_folder="../../templates")


@member_bp.route("/")
@member_required
def dashboard():
    now = datetime.utcnow()

    upcoming_seats = (SeatBooking.query.filter_by(user_id=current_user.id)
                      .filter(SeatBooking.end_at >= now,
                              SeatBooking.status.in_([BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN]))
                      .order_by(SeatBooking.start_at).limit(10).all())
    upcoming_rooms = (RoomBooking.query.filter_by(user_id=current_user.id)
                      .filter(RoomBooking.end_at >= now,
                              RoomBooking.status.in_([BookingStatus.CONFIRMED, BookingStatus.CHECKED_IN]))
                      .order_by(RoomBooking.start_at).limit(10).all())
    subs = Subscription.query.filter(
        (Subscription.user_id == current_user.id) |
        (Subscription.company_id == current_user.company_id),
        Subscription.status == SubscriptionStatus.ACTIVE,
    ).all()
    credits = sum(s.meeting_credits_balance for s in subs)
    invoices = (Invoice.query
                .filter((Invoice.user_id == current_user.id) |
                        (Invoice.company_id == current_user.company_id))
                .order_by(Invoice.issued_at.desc().nullslast()).limit(5).all())
    return render_template(
        "member/dashboard.html",
        upcoming_seats=upcoming_seats,
        upcoming_rooms=upcoming_rooms,
        credits=credits,
        subscriptions=subs,
        invoices=invoices,
    )


@member_bp.route("/bookings")
@member_required
def bookings():
    seat_bookings = (SeatBooking.query.filter_by(user_id=current_user.id)
                     .order_by(SeatBooking.start_at.desc()).limit(100).all())
    room_bookings = (RoomBooking.query.filter_by(user_id=current_user.id)
                     .order_by(RoomBooking.start_at.desc()).limit(100).all())
    return render_template("member/bookings.html",
                           seat_bookings=seat_bookings, room_bookings=room_bookings)


@member_bp.route("/bookings/seat/<int:booking_id>/cancel", methods=["POST"])
@member_required
def cancel_seat_booking(booking_id: int):
    booking = SeatBooking.query.get_or_404(booking_id)
    try:
        cancel_booking(booking, current_user)
        flash("Booking cancelled.", "info")
    except BookingError as e:
        flash(str(e), "warning")
    return redirect(url_for("member.bookings"))


@member_bp.route("/bookings/room/<int:booking_id>/cancel", methods=["POST"])
@member_required
def cancel_room_booking(booking_id: int):
    booking = RoomBooking.query.get_or_404(booking_id)
    try:
        cancel_booking(booking, current_user)
        flash("Booking cancelled.", "info")
    except BookingError as e:
        flash(str(e), "warning")
    return redirect(url_for("member.bookings"))
