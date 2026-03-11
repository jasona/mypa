# Google Calendar Setup

Google Calendar is used for availability checks and event creation, updates, and deletion.

## What You Need

- a Google account
- a Google Cloud project
- Calendar API enabled
- OAuth client credentials
- a refresh token with calendar scopes

## Required Scopes

This project uses:

- `https://www.googleapis.com/auth/calendar.readonly`
- `https://www.googleapis.com/auth/calendar.events`

## Create The Google Cloud App

1. Open Google Cloud Console.
2. Create or select a project.
3. Enable the Google Calendar API.
4. Configure the OAuth consent screen.
5. Create an OAuth client ID.
6. Copy the client ID and client secret.

Add them to `.env`:

```env
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_CALENDAR_ID=primary
```

## Obtain A Refresh Token

You need a refresh token for a user who has access to the target calendar.

Typical approaches:

- use the Google OAuth Playground
- run a one-time local OAuth helper script
- use your own existing auth tooling

Store the resulting refresh token in `.env`:

```env
GOOGLE_REFRESH_TOKEN=your_refresh_token
```

## Calendar ID

For most personal setups, `GOOGLE_CALENDAR_ID=primary` is correct.

Use a specific calendar ID if you want the agent to manage a dedicated calendar instead.

## Verification

After the app is running:

1. Send a Telegram message asking about availability.
2. Confirm the response reflects actual calendar data.
3. If you trigger an email flow that confirms a meeting, confirm the event appears in the configured calendar.

## Common Issues

- Simulated results instead of live calendar data: one or more Google credentials are missing
- Auth errors: refresh token is invalid, expired, or missing required scopes
- Wrong calendar being updated: `GOOGLE_CALENDAR_ID` points to the wrong calendar
