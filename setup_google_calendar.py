import argparse
import json
import os
from pathlib import Path

from dotenv import dotenv_values, set_key
from google.auth.exceptions import GoogleAuthError
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
PROJECT_DIR = Path(__file__).resolve().parent
ENV_FILE = PROJECT_DIR / ".env"


def main():
    parser = argparse.ArgumentParser(
        description="Authorize InternFlow to create review meetings in Google Calendar."
    )
    parser.add_argument(
        "client_secret_file",
        type=Path,
        help="Path to the OAuth client JSON downloaded from Google Cloud Console.",
    )
    args = parser.parse_args()
    client_file = args.client_secret_file.expanduser().resolve()
    if not client_file.is_file():
        parser.error(f"OAuth client JSON was not found: {client_file}")

    try:
        client_config = json.loads(client_file.read_text(encoding="utf-8"))
        if not any(key in client_config for key in ("installed", "web")):
            parser.error(
                "This is not a Google OAuth client JSON. Create a Desktop app OAuth client."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_file),
            scopes=SCOPES,
        )
        credentials = flow.run_local_server(
            host="127.0.0.1",
            port=0,
            open_browser=True,
            access_type="offline",
            prompt="consent",
        )
    except (OSError, json.JSONDecodeError, GoogleAuthError, ValueError) as exc:
        parser.error(f"Google OAuth setup failed: {exc}")

    if not credentials.refresh_token:
        parser.error(
            "Google did not return a refresh token. Revoke the app's access in your "
            "Google Account and rerun setup to grant offline Calendar access."
        )

    oauth = client_config.get("installed") or client_config.get("web") or {}
    ENV_FILE.touch(exist_ok=True)
    os.chmod(ENV_FILE, 0o600)
    set_key(str(ENV_FILE), "GOOGLE_CLIENT_ID", credentials.client_id or oauth["client_id"])
    set_key(
        str(ENV_FILE),
        "GOOGLE_CLIENT_SECRET",
        credentials.client_secret or oauth["client_secret"],
    )
    set_key(str(ENV_FILE), "GOOGLE_REFRESH_TOKEN", credentials.refresh_token)
    values = dotenv_values(ENV_FILE)
    if not values.get("GOOGLE_CALENDAR_ID"):
        set_key(str(ENV_FILE), "GOOGLE_CALENDAR_ID", "primary")
    if not values.get("GOOGLE_MEET_DURATION_MINUTES"):
        set_key(str(ENV_FILE), "GOOGLE_MEET_DURATION_MINUTES", "30")
    print("Google Calendar authorization succeeded.")
    print(f"OAuth settings saved to {ENV_FILE}; secret values were not displayed.")
    print("Restart InternFlow before scheduling review meetings.")


if __name__ == "__main__":
    main()
