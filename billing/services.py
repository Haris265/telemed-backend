from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import ClinicSubscription, Invoice, LedgerEntry, Payment, PurchaseRequest


def clinic_ledger_balance(clinic) -> Decimal:
    last = (
        LedgerEntry.objects.filter(clinic=clinic)
        .order_by("-created_at", "-id")
        .first()
    )
    return last.balance_after if last else Decimal("0.00")


def expire_subscriptions(clinic=None) -> int:
    """Mark past-due ACTIVE subscriptions as EXPIRED. Returns count updated."""
    today = timezone.localdate()
    qs = ClinicSubscription.objects.filter(
        status=ClinicSubscription.Status.ACTIVE,
        is_active=True,
        end_date__lt=today,
    )
    if clinic is not None:
        qs = qs.filter(clinic=clinic)
    return qs.update(status=ClinicSubscription.Status.EXPIRED, is_active=False)


def _current_or_latest_subscription(clinic):
    expire_subscriptions(clinic)
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
    if latest.status == ClinicSubscription.Status.PENDING_CLINIC:
        return latest, "pending_clinic"
    if latest.status == ClinicSubscription.Status.PENDING_PAYMENT:
        return latest, "pending_payment"
    if latest.end_date < today or latest.status == ClinicSubscription.Status.EXPIRED:
        return latest, "expired"
    if latest.status == ClinicSubscription.Status.CANCELLED:
        return latest, "none"
    return latest, "none"


def active_subscription_summary(clinic) -> dict | None:
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

    blocking = (
        Invoice.objects.filter(
            clinic=clinic,
            status__in=(
                Invoice.Status.PENDING,
                Invoice.Status.PENDING_VERIFICATION,
                Invoice.Status.OVERDUE,
            ),
        )
        .order_by("-created_at")
        .first()
    )
    due_amount = Decimal(blocking.amount) if blocking else Decimal("0.00")

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
            "due": str(due_amount),
            "paid_this_month": str(paid_this_month),
            "payment_status": "unpaid" if blocking else "n/a",
            "ledger_balance": str(balance),
        }

    price = Decimal(sub.package.price)
    amount_paid = Decimal(sub.amount_paid)
    if blocking:
        due = due_amount
        payment_status = (
            "pending_verification"
            if blocking.status == Invoice.Status.PENDING_VERIFICATION
            else "unpaid"
        )
    else:
        due = max(Decimal("0.00"), price - amount_paid)
        if package_status == "active" and due == 0:
            payment_status = "paid"
        elif package_status in ("pending_clinic", "pending_payment"):
            payment_status = "unpaid"
        elif package_status == "none":
            payment_status = "n/a"
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


def clinic_access_state(clinic) -> dict:
    """Lock clinic features until active package with no blocking unpaid invoice."""
    expire_subscriptions(clinic)
    today = timezone.localdate()

    pending_offer = (
        ClinicSubscription.objects.filter(
            clinic=clinic,
            status=ClinicSubscription.Status.PENDING_CLINIC,
            is_active=True,
        )
        .select_related("package")
        .order_by("-created_at")
        .first()
    )
    blocking_invoice = (
        Invoice.objects.filter(
            clinic=clinic,
            status__in=(
                Invoice.Status.PENDING,
                Invoice.Status.PENDING_VERIFICATION,
                Invoice.Status.OVERDUE,
            ),
        )
        .select_related("package", "subscription")
        .order_by("-created_at")
        .first()
    )
    active = (
        ClinicSubscription.objects.filter(
            clinic=clinic,
            status=ClinicSubscription.Status.ACTIVE,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        )
        .select_related("package")
        .order_by("-end_date")
        .first()
    )

    if pending_offer:
        reason = "awaiting_accept"
        locked = True
    elif blocking_invoice:
        reason = "awaiting_payment"
        locked = True
    elif not active:
        reason = "expired"
        locked = True
    else:
        reason = "none"
        locked = False

    return {
        "access_locked": locked,
        "lock_reason": reason,
        "pending_offer_uuid": str(pending_offer.uuid) if pending_offer else None,
        "blocking_invoice_uuid": str(blocking_invoice.uuid) if blocking_invoice else None,
        "has_active_package": bool(active),
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


def _period_for_package(package, start_date=None):
    today = timezone.localdate()
    start = start_date or today
    end = start + timedelta(days=max(int(package.duration_days), 1) - 1)
    return start, end


@transaction.atomic
def assign_package_offer(
    *,
    clinic,
    package,
    recorded_by,
    notes: str = "",
    start_date=None,
    amount: Decimal | None = None,
) -> ClinicSubscription:
    """Superadmin assigns a clinic-scoped package → pending clinic accept."""
    if package.clinic_id and package.clinic_id != clinic.id:
        raise ValueError("Package does not belong to this clinic.")

    # Cancel any previous pending offers for this clinic
    ClinicSubscription.objects.filter(
        clinic=clinic,
        status__in=(
            ClinicSubscription.Status.PENDING_CLINIC,
            ClinicSubscription.Status.PENDING_PAYMENT,
        ),
        is_active=True,
    ).update(status=ClinicSubscription.Status.CANCELLED, is_active=False)

    start, end = _period_for_package(package, start_date)
    return ClinicSubscription.objects.create(
        clinic=clinic,
        package=package,
        start_date=start,
        end_date=end,
        amount_paid=Decimal("0.00"),
        status=ClinicSubscription.Status.PENDING_CLINIC,
        is_active=True,
        notes=notes or (f"Assigned amount hint: {amount}" if amount is not None else ""),
    )


@transaction.atomic
def clinic_accept_offer(*, subscription: ClinicSubscription, accepted_by) -> tuple[ClinicSubscription, Invoice]:
    if subscription.status != ClinicSubscription.Status.PENDING_CLINIC:
        raise ValueError("Subscription is not awaiting clinic acceptance.")

    package = subscription.package
    start, end = subscription.start_date, subscription.end_date
    # Refresh period from today if offer sat too long
    today = timezone.localdate()
    if start < today:
        start, end = _period_for_package(package, today)
        subscription.start_date = start
        subscription.end_date = end

    subscription.status = ClinicSubscription.Status.PENDING_PAYMENT
    subscription.save(update_fields=["status", "start_date", "end_date", "updated_at"])

    invoice = Invoice.objects.create(
        clinic=subscription.clinic,
        package=package,
        subscription=subscription,
        period_start=start,
        period_end=end,
        amount=package.price,
        due_date=start,
        status=Invoice.Status.PENDING,
        notes="Invoice after clinic accepted package offer",
        created_by=accepted_by,
    )
    return subscription, invoice


@transaction.atomic
def clinic_reject_offer(*, subscription: ClinicSubscription) -> ClinicSubscription:
    if subscription.status != ClinicSubscription.Status.PENDING_CLINIC:
        raise ValueError("Subscription is not awaiting clinic acceptance.")
    subscription.status = ClinicSubscription.Status.REJECTED
    subscription.is_active = False
    subscription.save(update_fields=["status", "is_active", "updated_at"])
    return subscription


@transaction.atomic
def clinic_submit_invoice_payment(*, invoice: Invoice, notes: str = "") -> Invoice:
    if invoice.status not in (Invoice.Status.PENDING, Invoice.Status.OVERDUE):
        raise ValueError("Invoice cannot accept payment submission in its current status.")
    invoice.status = Invoice.Status.PENDING_VERIFICATION
    if notes:
        invoice.notes = f"{invoice.notes}\n{notes}".strip() if invoice.notes else notes
    invoice.save(update_fields=["status", "notes", "updated_at"])
    return invoice


@transaction.atomic
def superadmin_mark_invoice_paid(
    *,
    invoice: Invoice,
    recorded_by,
    notes: str = "",
) -> tuple[Payment, ClinicSubscription | None]:
    if invoice.status not in (
        Invoice.Status.PENDING,
        Invoice.Status.PENDING_VERIFICATION,
        Invoice.Status.OVERDUE,
    ):
        raise ValueError("Invoice is not payable.")

    clinic = invoice.clinic
    package = invoice.package
    amount = Decimal(invoice.amount)
    subscription = invoice.subscription

    ClinicSubscription.objects.filter(
        clinic=clinic,
        status=ClinicSubscription.Status.ACTIVE,
        is_active=True,
    ).exclude(pk=subscription.pk if subscription else None).update(
        status=ClinicSubscription.Status.CANCELLED,
        is_active=False,
    )

    if subscription:
        subscription.status = ClinicSubscription.Status.ACTIVE
        subscription.is_active = True
        subscription.amount_paid = amount
        subscription.start_date = invoice.period_start
        subscription.end_date = invoice.period_end
        if notes:
            subscription.notes = (
                f"{subscription.notes}\n{notes}".strip() if subscription.notes else notes
            )
        subscription.save(
            update_fields=[
                "status",
                "is_active",
                "amount_paid",
                "start_date",
                "end_date",
                "notes",
                "updated_at",
            ]
        )
    else:
        subscription = ClinicSubscription.objects.create(
            clinic=clinic,
            package=package,
            start_date=invoice.period_start,
            end_date=invoice.period_end,
            amount_paid=amount,
            status=ClinicSubscription.Status.ACTIVE,
            is_active=True,
            notes=notes,
        )
        invoice.subscription = subscription

    payment = Payment.objects.create(
        clinic=clinic,
        amount=amount,
        method=Payment.Method.CASH,
        status=Payment.Status.COMPLETED,
        purchase_request=invoice.purchase_request,
        subscription=subscription,
        invoice=invoice,
        recorded_by=recorded_by,
        paid_at=timezone.now(),
        notes=notes or f"Invoice {invoice.uuid} paid",
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

    invoice.status = Invoice.Status.PAID
    invoice.paid_at = timezone.now()
    if notes:
        invoice.notes = f"{invoice.notes}\n{notes}".strip() if invoice.notes else notes
    invoice.save(update_fields=["status", "paid_at", "notes", "subscription", "updated_at"])

    if invoice.purchase_request_id:
        pr = invoice.purchase_request
        if pr and pr.status == PurchaseRequest.Status.PENDING:
            pr.status = PurchaseRequest.Status.APPROVED
            pr.reviewed_by = recorded_by
            pr.reviewed_at = timezone.now()
            pr.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    return payment, subscription


@transaction.atomic
def approve_renewal_request(
    *,
    purchase_request: PurchaseRequest,
    reviewed_by,
    notes: str = "",
    start_date=None,
    amount: Decimal | None = None,
) -> Invoice:
    """Approve clinic renewal/purchase request by issuing an invoice (no auto-activate)."""
    if purchase_request.status != PurchaseRequest.Status.PENDING:
        raise ValueError("Purchase request is not pending.")

    clinic = purchase_request.clinic
    package = purchase_request.package
    if package.clinic_id and package.clinic_id != clinic.id:
        raise ValueError("Package does not belong to this clinic.")

    start, end = _period_for_package(package, start_date)
    invoice_amount = Decimal(amount) if amount is not None else Decimal(package.price)

    # Cancel prior pending payment subs
    ClinicSubscription.objects.filter(
        clinic=clinic,
        status__in=(
            ClinicSubscription.Status.PENDING_CLINIC,
            ClinicSubscription.Status.PENDING_PAYMENT,
        ),
        is_active=True,
    ).update(status=ClinicSubscription.Status.CANCELLED, is_active=False)

    subscription = ClinicSubscription.objects.create(
        clinic=clinic,
        package=package,
        start_date=start,
        end_date=end,
        amount_paid=Decimal("0.00"),
        status=ClinicSubscription.Status.PENDING_PAYMENT,
        is_active=True,
        notes=notes or "Renewal / purchase request approved — awaiting invoice payment",
    )

    invoice = Invoice.objects.create(
        clinic=clinic,
        package=package,
        subscription=subscription,
        purchase_request=purchase_request,
        period_start=start,
        period_end=end,
        amount=invoice_amount,
        due_date=start,
        status=Invoice.Status.PENDING,
        notes=notes or "Invoice from approved purchase/renewal request",
        created_by=reviewed_by,
    )

    purchase_request.status = PurchaseRequest.Status.APPROVED
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
    return invoice


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
    """Legacy helper — prefer assign_package_offer / mark_invoice_paid. Kept for admin tools."""
    if purchase_request is not None:
        invoice = approve_renewal_request(
            purchase_request=purchase_request,
            reviewed_by=recorded_by,
            notes=notes,
            start_date=start_date,
            amount=amount,
        )
        return superadmin_mark_invoice_paid(
            invoice=invoice, recorded_by=recorded_by, notes=notes
        )

    offer = assign_package_offer(
        clinic=clinic,
        package=package,
        recorded_by=recorded_by,
        notes=notes,
        start_date=start_date,
        amount=amount,
    )
    sub, invoice = clinic_accept_offer(subscription=offer, accepted_by=recorded_by)
    return superadmin_mark_invoice_paid(
        invoice=invoice, recorded_by=recorded_by, notes=notes
    )


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
