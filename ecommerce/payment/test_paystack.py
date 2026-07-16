from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from payment.services.paystack import (
    PAYSTACK_TIMEOUT_SECONDS,
    PaystackInvalidResponse,
    PaystackNetworkError,
    PaystackVerificationError,
    verify_transaction,
)


@override_settings(PAYSTACK_SECRET_KEY="test-secret-key")
class PaystackGatewayTests(SimpleTestCase):
    def payload(self, **overrides):
        data = {
            "id": 123456,
            "reference": "payment-reference",
            "status": "success",
            "amount": 12550,
            "currency": "NGN",
            "customer": {"email": "customer@example.com"},
            "paid_at": "2026-07-16T10:30:00Z",
            "channel": "card",
        }
        data.update(overrides)
        return {"status": True, "message": "Verification successful", "data": data}

    def response(self, *, status_code=200, payload=None):
        response = Mock(status_code=status_code)
        response.json.return_value = payload if payload is not None else self.payload()
        return response

    @patch("payment.services.paystack.requests.get")
    def test_successful_verification_is_normalized(self, request_get):
        request_get.return_value = self.response()

        result = verify_transaction("payment-reference")

        self.assertTrue(result.successful)
        self.assertEqual(result.reference, "payment-reference")
        self.assertEqual(result.amount_kobo, 12550)
        self.assertEqual(result.currency, "NGN")
        self.assertEqual(result.transaction_id, "123456")
        self.assertEqual(result.customer_email, "customer@example.com")
        self.assertEqual(result.channel, "card")
        self.assertIsNotNone(result.paid_at)

    @patch("payment.services.paystack.requests.get")
    def test_timeout_is_normalized(self, request_get):
        request_get.side_effect = requests.Timeout("timeout")
        with self.assertRaises(PaystackNetworkError):
            verify_transaction("payment-reference")

    @patch("payment.services.paystack.requests.get")
    def test_connection_error_is_normalized(self, request_get):
        request_get.side_effect = requests.ConnectionError("offline")
        with self.assertRaises(PaystackNetworkError):
            verify_transaction("payment-reference")

    @patch("payment.services.paystack.requests.get")
    def test_non_2xx_response_is_rejected(self, request_get):
        request_get.return_value = self.response(status_code=500)
        with self.assertRaises(PaystackVerificationError):
            verify_transaction("payment-reference")

    @patch("payment.services.paystack.requests.get")
    def test_invalid_json_is_rejected(self, request_get):
        response = self.response()
        response.json.side_effect = ValueError("invalid JSON")
        request_get.return_value = response

        with self.assertRaises(PaystackInvalidResponse):
            verify_transaction("payment-reference")

    @patch("payment.services.paystack.requests.get")
    def test_paystack_declared_failure_is_rejected(self, request_get):
        request_get.return_value = self.response(
            payload={"status": False, "message": "Verification failed"}
        )
        with self.assertRaises(PaystackVerificationError):
            verify_transaction("payment-reference")

    @patch("payment.services.paystack.requests.get")
    def test_missing_required_fields_are_rejected(self, request_get):
        request_get.return_value = self.response(payload=self.payload(id=None))
        with self.assertRaises(PaystackInvalidResponse):
            verify_transaction("payment-reference")

    @patch("payment.services.paystack.requests.get")
    def test_timeout_and_secret_header_are_explicit(self, request_get):
        request_get.return_value = self.response()

        verify_transaction("payment-reference")

        _, kwargs = request_get.call_args
        self.assertEqual(kwargs["timeout"], PAYSTACK_TIMEOUT_SECONDS)
        self.assertEqual(
            kwargs["headers"],
            {
                "Authorization": "Bearer test-secret-key",
                "Accept": "application/json",
            },
        )
        self.assertNotIn("test-secret-key", request_get.call_args.args[0])
