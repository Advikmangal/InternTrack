"""Google OAuth helpers and conservative recruitment-email classification."""
import base64
import hashlib
import html
import re
from datetime import timezone
import httpx
from fastapi import HTTPException
from .config import settings

GMAIL_SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
GMAIL_URL = 'https://gmail.googleapis.com/gmail/v1/users/me'
QUERY = '("application" OR "applied" OR "interview" OR "assessment" OR "job offer" OR "candidature") -category:promotions -category:social'


def configured():
    return bool(settings.google_client_id and settings.google_client_secret)


def cipher():
    from cryptography.fernet import Fernet
    try:
        return Fernet(settings.google_token_key.encode())
    except (ValueError, TypeError):
        raise HTTPException(503, 'Gmail token encryption is not configured') from None


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()


def google_request(method, url, **kwargs):
    try:
        response = httpx.request(method, url, timeout=20, **kwargs)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(404, 'Google message no longer exists') from None
        if exc.response.status_code in (400, 401, 403):
            raise HTTPException(409, 'Google access expired or was denied. Reconnect Google and grant Gmail access.') from None
        raise HTTPException(502, 'Google is temporarily unavailable. Please retry.') from None
    except (httpx.RequestError, ValueError):
        raise HTTPException(502, 'Could not contact Google. Please retry.') from None


def access_token(account):
    from cryptography.fernet import InvalidToken
    try:
        refresh = cipher().decrypt(account.refresh_token.encode()).decode()
    except InvalidToken:
        raise HTTPException(409, 'Reconnect Gmail: the stored connection cannot be decrypted.') from None
    result = google_request('POST', TOKEN_URL, data={
        'client_id': settings.google_client_id, 'client_secret': settings.google_client_secret,
        'refresh_token': refresh, 'grant_type': 'refresh_token',
    })
    if not result.get('access_token'):
        raise HTTPException(502, 'Google did not return an access token')
    if result.get('refresh_token'):
        account.refresh_token = cipher().encrypt(result['refresh_token'].encode()).decode()
    return result['access_token']


def classify(subject, snippet):
    text = html.unescape(subject + ' ' + snippet)
    if re.search(r'job alert|recommended jobs|jobs for you|new jobs|jobs you might', subject, re.I):
        return None
    patterns = [
        ('Rejected', r'not (?:be )?(?:moving|proceeding) forward|unfortunately|not been selected|unsuccessful'),
        ('Offer', r'offer of employment|job offer|pleased to offer'),
        ('Interview', r'interview (?:invitation|scheduled|with|for)|invite you to (?:an? )?interview'),
        ('Assessment', r'(?:complete|online|coding|technical) assessment|assessment invitation'),
        ('Applied', r'application (?:was |has been )?(?:sent|submitted|received)|thank you for (?:applying|your application)|you applied|successfully applied'),
    ]
    status = next((status for status, pattern in patterns if re.search(pattern, text, re.I)), None)
    if not status:
        return None
    company = role = ''
    match = re.search(r'(?:you applied (?:for|to)|application (?:sent|submitted) for)\s+(.+?)\s+at\s+(.+?)(?:[.!]|$)', subject, re.I)
    if match:
        role, company = (part.strip()[:160] for part in match.groups())
    return {'suggested_status': status, 'company': company, 'role': role}
