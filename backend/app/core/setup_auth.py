"""Create the one-advocate credentials for backend/.env without storing a plaintext password."""

import getpass
import os
from pathlib import Path
import re
import secrets
import tempfile

from app.core.auth import hash_password
from app.core.encryption import generate_encryption_key


def main() -> None:
    email = input("Advocate email: ").strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise SystemExit("Enter a valid advocate email address.")
    password = getpass.getpass("Choose a password (at least 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match.")
    try:
        password_hash = hash_password(password)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    env_path = Path(__file__).resolve().parents[2] / ".env"
    existing = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    current_values = {}
    for line in existing:
        match = re.match(r"^\s*([A-Z_]+)\s*=(.*)$", line)
        if match:
            current_values[match.group(1)] = match.group(2).strip()
    values = {
        "ADVOCATE_EMAIL": email,
        "ADVOCATE_PASSWORD_HASH": password_hash,
        "SESSION_SECRET": secrets.token_urlsafe(48),
        "APP_ENCRYPTION_KEY": current_values.get("APP_ENCRYPTION_KEY") or generate_encryption_key(),
    }
    written: set[str] = set()
    output: list[str] = []
    for line in existing:
        match = re.match(r"^\s*([A-Z_]+)\s*=", line)
        key = match.group(1) if match else ""
        if key in values:
            if key not in written:
                value = values[key]
                # Compose interprets `$` even in values it does not otherwise
                # use. Quote the scrypt hash so its separators stay literal in
                # both Compose's root .env and Pydantic's backend/.env.
                if key == "ADVOCATE_PASSWORD_HASH":
                    value = f"'{value}'"
                output.append(f"{key}={value}")
                written.add(key)
        else:
            output.append(line)
    for key, value in values.items():
        if key not in written:
            if key == "ADVOCATE_PASSWORD_HASH":
                value = f"'{value}'"
            output.append(f"{key}={value}")
    payload = "\n".join(output).rstrip() + "\n"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".env.", dir=env_path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as destination:
            destination.write(payload)
        os.replace(temporary_name, env_path)
    except Exception:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    print(f"Single-advocate sign-in was configured in {env_path}.")
    print("The password was stored only as a scrypt hash; a random application encryption key was configured if none existed.")
    print("Keep backend/.env private and backed up securely. Changing APP_ENCRYPTION_KEY makes encrypted case data unreadable.")
    print("Restart the API to apply these settings.")


if __name__ == "__main__":
    main()
