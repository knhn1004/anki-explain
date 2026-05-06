"""macOS Keychain wrapper via the `security` CLI.

Service: anki-explain
Account: openrouter
"""
from __future__ import annotations

import subprocess

SERVICE = "anki-explain"
ACCOUNT = "openrouter"


class KeychainError(RuntimeError):
    pass


def get_api_key() -> str | None:
    """Return the stored OpenRouter API key, or None if not set."""
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise KeychainError("`security` CLI not found (not on macOS?)") from e

    if result.returncode == 0:
        return result.stdout.strip() or None
    if "could not be found" in (result.stderr or ""):
        return None
    raise KeychainError(f"keychain read failed: {result.stderr.strip()}")


def set_api_key(key: str) -> None:
    """Write/overwrite the OpenRouter API key in Keychain."""
    if not key or not key.strip():
        raise ValueError("empty key")
    try:
        result = subprocess.run(
            [
                "security", "add-generic-password",
                "-s", SERVICE,
                "-a", ACCOUNT,
                "-w", key.strip(),
                "-U",  # update if exists
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise KeychainError("`security` CLI not found (not on macOS?)") from e
    if result.returncode != 0:
        raise KeychainError(f"keychain write failed: {result.stderr.strip()}")


def delete_api_key() -> None:
    subprocess.run(
        ["security", "delete-generic-password", "-s", SERVICE, "-a", ACCOUNT],
        capture_output=True,
        text=True,
        check=False,
    )
