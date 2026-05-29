#!/usr/bin/env python3
"""Generate app secrets for .env without printing provider API keys."""
from __future__ import annotations

import secrets
from cryptography.fernet import Fernet

print("APP_ENCRYPTION_KEY=" + Fernet.generate_key().decode())
print("JWT_SECRET_KEY=" + secrets.token_urlsafe(48))
