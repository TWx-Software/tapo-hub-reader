"""Store Tapo credentials in the operating system's credential vault."""

from __future__ import annotations

import keyring

from .config import APP_NAME


class CredentialError(RuntimeError):
    """A credential could not be read or safely stored."""


def _usable_keyring():
    try:
        backend = keyring.get_keyring()
        if backend.priority <= 0:
            raise CredentialError(
                "No secure keyring backend is available. Unlock or install your "
                "desktop keyring (KDE Wallet, GNOME Keyring, or Secret Service)."
            )
        return backend
    except CredentialError:
        raise
    except Exception as exc:
        raise CredentialError(f"Could not access the system keyring: {exc}") from exc


def save_password(username: str, password: str) -> None:
    _usable_keyring()
    try:
        keyring.set_password(APP_NAME, username, password)
    except Exception as exc:
        raise CredentialError(
            "Could not save the password in the system keyring. Check that your "
            "desktop keyring is running and unlocked."
        ) from exc


def get_password(username: str) -> str | None:
    _usable_keyring()
    try:
        return keyring.get_password(APP_NAME, username)
    except Exception as exc:
        raise CredentialError(
            "Could not read the password from the system keyring. Check that your "
            "desktop keyring is unlocked."
        ) from exc


def delete_password(username: str) -> None:
    _usable_keyring()
    try:
        keyring.delete_password(APP_NAME, username)
    except keyring.errors.PasswordDeleteError:
        return
    except Exception as exc:
        raise CredentialError(
            "Could not remove the password from the system keyring."
        ) from exc
