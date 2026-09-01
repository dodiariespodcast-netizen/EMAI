"""Templated notifications for the events physicians and admins actually
care about. Each function takes plain values (not ORM objects) so it stays
easy to call from any route or background job without import cycles."""

from __future__ import annotations

from app.services.notifications.email import send_email


def notify_time_off_status_changed(physician_email: str, physician_name: str, start_date, end_date, status: str) -> None:
    send_email(
        to=physician_email,
        subject=f"Time-off request {status}: {start_date} to {end_date}",
        body=(
            f"Hi {physician_name},\n\n"
            f"Your time-off request for {start_date} through {end_date} has been {status}.\n\n"
            "-- EMAI Scheduler"
        ),
    )


def notify_schedule_published(physician_email: str, physician_name: str, period_start, period_end, shift_count: int) -> None:
    send_email(
        to=physician_email,
        subject=f"Schedule published: {period_start} to {period_end}",
        body=(
            f"Hi {physician_name},\n\n"
            f"The schedule for {period_start} through {period_end} has been published. "
            f"You're on {shift_count} shift(s) this period. Log in to see the full schedule "
            "or subscribe your calendar to see it in your phone's calendar app.\n\n"
            "-- EMAI Scheduler"
        ),
    )


def notify_swap_claimed(offering_email: str, offering_name: str, claimant_name: str, shift_date) -> None:
    send_email(
        to=offering_email,
        subject=f"Your {shift_date} shift swap was claimed",
        body=(
            f"Hi {offering_name},\n\n"
            f"{claimant_name} has claimed your {shift_date} shift. It's now pending scheduler approval.\n\n"
            "-- EMAI Scheduler"
        ),
    )


def notify_swap_decided(email: str, name: str, shift_date, approved: bool) -> None:
    outcome = "approved" if approved else "rejected"
    send_email(
        to=email,
        subject=f"Shift swap {outcome}: {shift_date}",
        body=f"Hi {name},\n\nThe shift swap for {shift_date} was {outcome} by a scheduler.\n\n-- EMAI Scheduler",
    )


def notify_credential_expiring(email: str, name: str, credential_type: str, expires_on) -> None:
    send_email(
        to=email,
        subject=f"Credential expiring soon: {credential_type}",
        body=(
            f"Hi {name},\n\n"
            f"Your {credential_type} expires on {expires_on}. Please renew and update your record "
            "to avoid a gap in your scheduling eligibility.\n\n"
            "-- EMAI Scheduler"
        ),
    )
