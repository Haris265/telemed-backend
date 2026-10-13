from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import ClinicSubscription, LedgerEntry, Payment, PurchaseRequest


def clinic_ledger_balance(clinic) -> Decimal:
    last = (
        LedgerEntry.objects.filter(clinic=clinic)
        .order_by("-created_at", "-id")
        .first()
    )
    return last.balance_after if last else Decimal("0.00")


def _current_or_latest_subscription(clinic):
    today = timezone.localdate()
    active = (
        ClinicSubscription.objects.filter(
            clinic=clinic,
            status=ClinicSubscription.Status.ACTIVE,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        )
        .select_related("package")
        .order_by("-end_date", "-id")
        .first()
    )
    if active:
        return active, "active"
    latest = (
        ClinicSubscription.objects.filter(clinic=clinic)
        .select_related("package")
        .order_by("-end_date", "-id")
        .first()
    )
    if not latest:
        return None, "none"
    if latest.end_date < today or latest.status == ClinicSubscription.Status.EXPIRED:
        return latest, "expired"
    if latest.status == ClinicSubscription.Status.CANCELLED:
        return latest, "none"
    return latest, "none"


def active_subscription_summary(clinic) -> dict | None:
    """Current valid clinic package: name, duration, expiry, renew-by."""
    sub, status = _current_or_latest_subscription(clinic)
    if status != "active" or not sub:
        return None
    end = sub.end_date.isoformat()
    return {
        "package_name": sub.package.name,
        "package_code": sub.package.code,
        "duration_days": sub.package.duration_days,
        "start_date": sub.start_date.isoformat(),
        "end_date": end,
        "renew_by": end,
    }


def clinic_payment_summary(clinic) -> dict:
    """Package + payment status for clinics/ledger UI."""
    today = timezone.localdate()
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(datetime.combine(month_start, datetime.min.time()))

    paid_this_month = (
        Payment.objects.filter(
            clinic=clinic,
            status=Payment.Status.COMPLETED,
            method=Payment.Method.CASH,
            paid_at__gte=month_start_dt,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    balance = clinic_ledger_balance(clinic)
    sub, package_status = _current_or_latest_subscription(clinic)

    if not sub:
        return {
            "package_status": "none",
            "package_name": None,
            "package_code": None,
            "duration_days": None,
            "start_date": None,
            "end_date": None,
            "renew_by": None,
            "package_price": None,
            "amount_paid": None,
            "due": "0.00",
            "paid_this_month": str(paid_this_month),
            "payment_status": "n/a",
            "ledger_balance": str(balance),
        }

    price = Decimal(sub.package.price)
    amount_paid = Decimal(sub.amount_paid)
    due = max(Decimal("0.00"), price - amount_paid)
    if package_status == "none":
        payment_status = "n/a"
    elif due == 0:
        payment_status = "paid"
    elif due >= price:
        payment_status = "unpaid"
    else:
        payment_status = "partial"

    end = sub.end_date.isoformat()
    return {
        "package_status": package_status,
        "package_name": sub.package.name,
        "package_code": sub.package.code,
        "duration_days": sub.package.duration_days,
        "start_date": sub.start_date.isoformat(),
        "end_date": end,
        "renew_by": end if package_status == "active" else None,
        "package_price": str(price),
        "amount_paid": str(amount_paid),
        "due": str(due),
        "paid_this_month": str(paid_this_month),
        "payment_status": payment_status,
        "ledger_balance": str(balance),
    }


def _append_ledger(
    *,
    clinic,
    entry_type: str,
    amount: Decimal,
    created_by,
    payment=None,
    subscription=None,
    notes: str = "",
) -> LedgerEntry:
    balance = clinic_ledger_balance(clinic) + amount
    return LedgerEntry.objects.create(
        clinic=clinic,
        entry_type=entry_type,
        amount=amount,
        balance_after=balance,
        payment=payment,
        subscription=subscription,
        notes=notes,
        created_by=created_by,
    )


@transaction.atomic
def confirm_cash_purchase(
    *,
    clinic,
    package,
    amount: Decimal,
    recorded_by,
    purchase_request: PurchaseRequest | None = None,
    notes: str = "",
    start_date=None,
) -> tuple[Payment, ClinicSubscription]:
    """
    Record cash payment, write ledger rows, activate clinic subscription.
    """
    if purchase_request is not None:
        if purchase_request.status != PurchaseRequest.Status.PENDING:
            raise ValueError("Purchase request is not pending.")
        if purchase_request.clinic_id != clinic.id:
            raise ValueError("Purchase request clinic mismatch.")
        if purchase_request.package_id != package.id:
            raise ValueError("Purchase request package mismatch.")

    # Deactivate overlapping active subscriptions for this clinic
    today = timezone.localdate()
    start = start_date or today
    end = start + timedelta(days=max(int(package.duration_days), 1) - 1)

    ClinicSubscription.objects.filter(
        clinic=clinic,
        status=ClinicSubscription.Status.ACTIVE,
        is_active=True,
    ).update(status=ClinicSubscription.Status.CANCELLED, is_active=False)

    subscription = ClinicSubscription.objects.create(
        clinic=clinic,
        package=package,
        start_date=start,
        end_date=end,
        amount_paid=amount,
        status=ClinicSubscription.Status.ACTIVE,
        is_active=True,
        notes=notes,
    )

    payment = Payment.objects.create(
        clinic=clinic,
        amount=amount,
        method=Payment.Method.CASH,
        status=Payment.Status.COMPLETED,
        purchase_request=purchase_request,
        subscription=subscription,
        recorded_by=recorded_by,
        paid_at=timezone.now(),
        notes=notes,
    )

    _append_ledger(
        clinic=clinic,
        entry_type=LedgerEntry.EntryType.PAYMENT_IN,
        amount=amount,
        created_by=recorded_by,
        payment=payment,
        subscription=subscription,
        notes=f"Cash payment for {package.name}",
    )
    _append_ledger(
        clinic=clinic,
        entry_type=LedgerEntry.EntryType.PACKAGE_CHARGE,
        amount=-Decimal(package.price),
        created_by=recorded_by,
        payment=payment,
        subscription=subscription,
        notes=f"Package charge: {package.name}",
    )

    if purchase_request is not None:
        purchase_request.status = PurchaseRequest.Status.APPROVED
        purchase_request.reviewed_by = recorded_by
        purchase_request.reviewed_at = timezone.now()
        purchase_request.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"]
        )

    return payment, subscription


@transaction.atomic
def reject_purchase_request(*, purchase_request: PurchaseRequest, reviewed_by, notes: str = ""):
    if purchase_request.status != PurchaseRequest.Status.PENDING:
        raise ValueError("Purchase request is not pending.")
    purchase_request.status = PurchaseRequest.Status.REJECTED
    purchase_request.reviewed_by = reviewed_by
    purchase_request.reviewed_at = timezone.now()
    if notes:
        purchase_request.notes = (
            f"{purchase_request.notes}\n{notes}".strip()
            if purchase_request.notes
            else notes
        )
    purchase_request.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "notes", "updated_at"]
    )
    return purchase_request


@transaction.atomic
def add_ledger_adjustment(*, clinic, amount: Decimal, created_by, notes: str = "") -> LedgerEntry:
    return _append_ledger(
        clinic=clinic,
        entry_type=LedgerEntry.EntryType.ADJUSTMENT,
        amount=amount,
        created_by=created_by,
        notes=notes or "Manual adjustment",
    )


def cash_collected_since(since) -> Decimal:
    total = (
        Payment.objects.filter(
            status=Payment.Status.COMPLETED,
            method=Payment.Method.CASH,
            paid_at__gte=since,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )
    return total
