"""Credential encryption boundary (docs/07-system-architecture.md's
Credential Vault, docs/06-data-model.md's CREDENTIAL.encrypted_value).

Plaintext credential values only ever exist transiently in memory here and
at the single call site that injects them into an authenticated tool
request -- never logged, never returned by any API response, never handed
to the Claude Code/Codex runner as a long-lived context value (its tool
calls may be traced/logged; a credential shouldn't be recoverable from
that trace -- see docs/07-system-architecture.md's Credential Vault
section).

Key management: CREDENTIAL_VAULT_KEY in .env is a Fernet key (32 url-safe
base64 bytes). This is an MVP-scope choice, not a hardened one -- rotating
to an OS-keychain-backed key or a dedicated secrets manager is explicitly
a later decision (docs/10-build-plan.md Phase 2, docs/09-...md's Appendix
note on multi-tenant credential vault hardening being out of MVP scope).
"""
from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class VaultNotConfigured(RuntimeError):
    pass


def _fernet() -> Fernet:
    if not settings.credential_vault_key:
        raise VaultNotConfigured(
            "CREDENTIAL_VAULT_KEY is not set. Generate one with: "
            "python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(settings.credential_vault_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt credential -- wrong key or corrupted value.") from exc
