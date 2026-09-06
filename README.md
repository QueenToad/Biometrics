# Biometrics

Pulls sleep, recovery and activity from Whoop and Oura, and writes one Notion
page per day so the morning check-in has fresh numbers already waiting.

Each day's page carries a section per device. The two are kept apart rather
than merged into one set of numbers: they measure differently, and the gap
between them is itself worth seeing.

Requires Python 3.9 or newer.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

- **Whoop** — create an app at https://developer-dashboard.whoop.com
- **Oura** — create an app at https://cloud.ouraring.com/oauth/applications
- **Notion** — create an internal integration at https://notion.so/profile/integrations,
  copy its token, then open the parent page and share it with that integration
  (`•••` → Connections). Without that share the API returns 404 for a page that
  plainly exists.

The redirect URI in `.env` must match what each provider has registered,
character for character, or the token exchange fails with `redirect_uri_mismatch`.

Then authorize:

```bash
python -m src.auth
```

## Usage

```bash
python -m src.main --days 7           # show the last week
python -m src.main --days 7 --json    # same, as JSON
python -m src.main --days 3 --sync    # ...and write it into Notion
```

## Daily sync

```bash
./scripts/install-schedule.sh          # 08:30 daily; SYNC_HOUR/SYNC_MINUTE to change
launchctl kickstart -p gui/$UID/com.biometrics.sync   # run it now
tail -f logs/sync.log
```

Each run re-syncs a few overlapping days, so a day missed while the laptop was
closed is filled in on the next run, and a re-sync corrects a day in place
rather than duplicating it.

## Notes on the data

- **Days are keyed on when you woke up**, not when you fell asleep, so a night
  and the recovery scored that same morning land on one page.
- **Oura's daily activity is a whole-day rollup**, not a session. It counts
  toward the day's calories but is not listed as a workout.
- **Times are local**, converted from the UTC that Whoop reports using the
  offset it sends alongside. Bedtime in UTC would be off by hours.
- **Sleep hours exclude time awake in bed.** Whoop's in-bed total counts awake
  and no-data spans; those are subtracted.
- **Naps are separated from nights.** A nap sets the `Дневной сон` checkbox
  instead of overwriting the night's numbers.
- **Unscored nights stay empty.** Whoop leaves a score null while a night is
  still `PENDING_SCORE` or is `UNSCORABLE`.

## Project structure

```
src/
├── auth.py              # OAuth2 flows, token refresh
├── main.py              # CLI
├── aggregate.py         # per-provider records -> one row per day
├── config.py            # env-backed settings
├── connectors/
│   ├── whoop.py         # Whoop API v2
│   ├── oura.py          # Oura API v2
│   └── notion.py        # one Notion page per day
└── models/              # sleep, recovery, activity, daily
scripts/
├── sync.sh              # what the scheduled job runs
└── install-schedule.sh  # registers it with launchd
```

## Something not working?

```bash
python -m src.doctor
```

Reports whether `.env` parses, what each credential looks like (length and
first/last characters — never the value), and whether each provider has a
renewable token.
