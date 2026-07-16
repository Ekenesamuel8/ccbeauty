import logging
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from urllib.parse import quote

import requests
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime


logger = logging.getLogger(__name__)
PAYSTACK_API_BASE_URL = "https://api.paystack.co"
PAYSTACK_TIMEOUT_SECONDS = 10


class PaystackError(Exception):
    """Base exception for safe Paystack gateway failures."""


class PaystackNetworkError(PaystackError):
    pass


class PaystackVerificationError(PaystackError):
    pass


class PaystackInvalidResponse(PaystackError):
    pass


@dataclass(frozen=True)
class PaystackVerificationResult:
    reference: str
    status: str
    amount_kobo: int
    currency: str
    customer_email: str | None
    transaction_id: str
    paid_at: datetime | None
    channel: str | None

    @property
    def successful(self) -> bool:
        return self.status == "success"


def _parse_paid_at(value) -> datetime | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise PaystackInvalidResponse("Paystack paid timestamp is invalid")
    parsed = parse_datetime(value)
    if parsed is None:
        raise PaystackInvalidResponse("Paystack paid timestamp is invalid")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed


def _normalize_response(payload) -> PaystackVerificationResult:
    if not isinstance(payload, dict):
        raise PaystackInvalidResponse("Paystack response must be an object")
    if payload.get("status") is not True:
        raise PaystackVerificationError("Paystack declined the verification request")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise PaystackInvalidResponse("Paystack response data is missing")

    reference = data.get("reference")
    status = data.get("status")
    amount = data.get("amount")
    currency = data.get("currency")
    transaction_id = data.get("id")
    if not isinstance(reference, str) or not reference:
        raise PaystackInvalidResponse("Paystack reference is missing")
    if not isinstance(status, str) or not status:
        raise PaystackInvalidResponse("Paystack transaction status is missing")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise PaystackInvalidResponse("Paystack amount is invalid")
    if not isinstance(currency, str) or not currency:
        raise PaystackInvalidResponse("Paystack currency is missing")
    if transaction_id in (None, ""):
        raise PaystackInvalidResponse("Paystack transaction ID is missing")

    customer = data.get("customer")
    customer_email = None
    if isinstance(customer, dict) and isinstance(customer.get("email"), str):
        customer_email = customer["email"]

    channel = data.get("channel")
    if channel is not None and not isinstance(channel, str):
        raise PaystackInvalidResponse("Paystack channel is invalid")

    return PaystackVerificationResult(
        reference=reference,
        status=status.lower(),
        amount_kobo=amount,
        currency=currency.upper(),
        customer_email=customer_email,
        transaction_id=str(transaction_id),
        paid_at=_parse_paid_at(data.get("paid_at")),
        channel=channel,
    )


def verify_transaction(reference: str) -> PaystackVerificationResult:
    if not isinstance(reference, str) or not reference:
        raise PaystackVerificationError("A payment reference is required")

    logger.info("Paystack verification started reference=%s", reference)
    url = f"{PAYSTACK_API_BASE_URL}/transaction/verify/{quote(reference, safe='')}"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Accept": "application/json",
    }
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=PAYSTACK_TIMEOUT_SECONDS,
        )
    except requests.Timeout as exc:
        logger.warning("Paystack verification timed out reference=%s", reference)
        raise PaystackNetworkError("Paystack verification timed out") from exc
    except requests.ConnectionError as exc:
        logger.warning("Paystack connection failed reference=%s", reference)
        raise PaystackNetworkError("Paystack connection failed") from exc
    except requests.RequestException as exc:
        logger.warning("Paystack request failed reference=%s", reference)
        raise PaystackNetworkError("Paystack verification request failed") from exc

    if not 200 <= response.status_code < 300:
        logger.warning(
            "Paystack returned HTTP %s reference=%s",
            response.status_code,
            reference,
        )
        raise PaystackVerificationError("Paystack verification was not accepted")

    try:
        payload = response.json()
    except ValueError as exc:
        logger.warning("Paystack returned invalid JSON reference=%s", reference)
        raise PaystackInvalidResponse("Paystack returned invalid JSON") from exc

    result = _normalize_response(payload)
    logger.info(
        "Paystack verification completed reference=%s status=%s transaction_id=%s",
        reference,
        result.status,
        result.transaction_id,
    )
    return result


def webhook_signature_is_valid(raw_body: bytes, signature: str | None) -> bool:
    if not isinstance(raw_body, bytes) or not isinstance(signature, str):
        return False
    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
