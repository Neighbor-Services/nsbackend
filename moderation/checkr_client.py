"""
Checkr API client for Neighbor Service.

Docs: https://docs.checkr.com/
All calls use HTTP Basic Auth with the API key as the username, empty password.
"""

import logging
import hmac
import hashlib
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

CHECKR_BASE_URL = 'https://api.checkr.com'


def _get_auth():
    """Returns (api_key, '') tuple for HTTP Basic Auth."""
    return (settings.CHECKR_API_KEY, '')


def _make_request(method: str, url: str, json_payload: dict = None, timeout: int = 30) -> requests.Response:
    """Helper to perform requests with standard headers, connection close, and retry logic on connection errors."""
    import time
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Connection': 'close',
    }
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=_get_auth(),
                json=json_payload,
                headers=headers,
                timeout=timeout,
            )
            return response
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            logger.warning(
                "Checkr API request connection issue (attempt %s/%s) for %s: %s",
                attempt + 1, max_retries, url, e
            )
            if attempt == max_retries - 1:
                raise
            time.sleep(1 * (attempt + 1))


def _handle_response(response: requests.Response, context: str) -> dict:
    """Raise a descriptive exception on non-2xx responses."""
    try:
        data = response.json()
    except Exception:
        data = {'raw': response.text}

    if not response.ok:
        error_msg = data.get('error', data.get('message', str(data)))
        logger.error(
            "Checkr API error [%s] HTTP %s: %s",
            context, response.status_code, error_msg
        )
        raise CheckrAPIError(
            f"Checkr [{context}] HTTP {response.status_code}: {error_msg}"
        )

    return data


class CheckrAPIError(Exception):
    """Raised when the Checkr API returns a non-2xx response."""
    pass


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------

def create_candidate(profile) -> dict:
    """
    Create a Checkr candidate from the provider's Profile.

    Returns the full Checkr candidate object dict.
    Raises CheckrAPIError on failure.
    """
    payload = {
        'email': profile.user.email,
    }

    # Optional enrichment — Checkr accepts these but does not require them
    if profile.first_name:
        payload['first_name'] = profile.first_name
    if profile.last_name:
        payload['last_name'] = profile.last_name
    # Note: phone and DOB are encrypted fields; avoid decrypting here unless
    # strictly necessary. Checkr collects SSN/DOB via the invitation form.

    logger.info("Creating Checkr candidate for user %s", profile.user.email)

    response = _make_request(
        'POST',
        f"{CHECKR_BASE_URL}/v1/candidates",
        json_payload=payload,
        timeout=30,
    )
    return _handle_response(response, 'create_candidate')


# ---------------------------------------------------------------------------
# Invitation (Checkr-hosted form flow)
# ---------------------------------------------------------------------------

def create_invitation(candidate_id: str, package: str, work_location: dict) -> dict:
    """
    Create a Checkr invitation for the given candidate.

    `work_location` must contain at least one of:
        {'state': 'CA'} or {'city': 'Los Angeles', 'state': 'CA', 'zipcode': '90001'}

    Returns the full Checkr invitation object dict (includes `invitation_url`).
    Raises CheckrAPIError on failure.
    """
    payload = {
        'candidate_id': candidate_id,
        'package': package,
        'work_locations': [work_location],
    }

    logger.info(
        "Creating Checkr invitation for candidate %s, package=%s",
        candidate_id, package
    )

    response = _make_request(
        'POST',
        f"{CHECKR_BASE_URL}/v1/invitations",
        json_payload=payload,
        timeout=30,
    )
    return _handle_response(response, 'create_invitation')


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def get_report(report_id: str) -> dict:
    """
    Fetch a Checkr report by ID.

    Returns the full report object dict.
    Raises CheckrAPIError on failure.
    """
    logger.info("Fetching Checkr report %s", report_id)

    response = _make_request(
        'GET',
        f"{CHECKR_BASE_URL}/v1/reports/{report_id}",
        timeout=30,
    )
    return _handle_response(response, 'get_report')


def get_candidate(candidate_id: str) -> dict:
    """Fetch a Checkr candidate by ID."""
    response = _make_request(
        'GET',
        f"{CHECKR_BASE_URL}/v1/candidates/{candidate_id}",
        timeout=30,
    )
    return _handle_response(response, 'get_candidate')


# ---------------------------------------------------------------------------
# Webhook signature verification
# ---------------------------------------------------------------------------

def verify_webhook_signature(payload_body: bytes, signature_header: str) -> bool:
    """
    Verify that the incoming webhook is genuinely from Checkr.

    Checkr sends an `X-Checkr-Signature` header containing an HMAC-SHA256
    digest (hex) of the raw request body, keyed with your webhook secret.

    Returns True if valid, False otherwise.
    """
    secret = getattr(settings, 'CHECKR_WEBHOOK_SECRET', '')
    if not secret:
        # If no secret is configured, skip verification (dev only).
        logger.warning(
            "CHECKR_WEBHOOK_SECRET not set — skipping webhook signature verification."
        )
        return True

    expected = hmac.new(
        secret.encode('utf-8'),
        payload_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header or '')
