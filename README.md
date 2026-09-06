# Biometrics

Whoop & Oura API integration — aggregate biometric data from wearables.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in your API credentials:
```bash
cp .env.example .env
```

3. Get your API credentials:
   - **Whoop**: Create an app at https://developer.whoop.com — get Client ID & Secret
   - **Oura**: Create an app at https://cloud.ouraring.com/oauth/applications — get Client ID & Secret

## Usage

```bash
# Start the OAuth flow to connect your accounts
python -m src.auth

# Fetch your latest data
python -m src.main
```

## Project Structure

```
src/
├── auth.py              # OAuth2 flows for Whoop & Oura
├── main.py              # CLI entry point
├── config.py            # Configuration & env vars
├── connectors/
│   ├── whoop.py         # Whoop API client
│   └── oura.py          # Oura API client
└── models/
    ├── sleep.py          # Unified sleep data model
    ├── recovery.py       # Recovery/readiness model
    └── activity.py       # Activity/workout model
```
