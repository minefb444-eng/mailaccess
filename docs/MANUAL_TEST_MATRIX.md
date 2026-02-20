# Manual Validation Matrix (Telegram + Web Shared Data)

Use this matrix after deployment to validate end-to-end behavior.

## Preconditions

- Bot process running.
- Web process running.
- Same `SESSION_FILE` configured for both.
- Valid mail credentials available for testing.

## Test Cases

### 1. Web login / account connect

1. Open `/login`.
2. Submit valid email/password.
3. Open `/accounts`.

Expected:
- Login succeeds.
- Account appears in connected account list.

### 2. Web inbox and mail detail

1. Open account inbox from `/accounts`.
2. Open any message.

Expected:
- Inbox lists messages.
- Mail details display sender/subject/time.
- OTP appears when present.
- Full-email link opens worker URL.

### 3. Telegram login and inbox still works

1. In Telegram bot, run login flow for another test account.
2. Open connected mails and inbox.

Expected:
- Existing Telegram behavior unchanged.
- Inbox navigation/search/read still works.

### 4. Shared account state consistency

1. Connect account in channel A.
2. Verify account exists for same identity context in channel B.
3. Disconnect in channel B.
4. Refresh channel A list/inbox.

Expected:
- Adds/removals persist to shared backend data.
- Channel A reflects removed account after refresh.

### 5. Web CSRF validation

1. Submit a POST form with missing/invalid CSRF token (via dev tools or crafted request).

Expected:
- Request is rejected (HTTP 400).

### 6. Web rate limit validation

1. Submit repeated login attempts above configured threshold within window.

Expected:
- Endpoint responds with HTTP 429 until window passes.

### 7. Session expiry check

1. Lower `WEB_SESSION_MAX_AGE_SECONDS`.
2. Login and wait until expiry.
3. Try opening `/accounts`.

Expected:
- User is redirected to `/login`.

### 8. Recovery check

1. Restart both services.
2. Re-open Telegram and web pages.

Expected:
- Previously persisted sessions/accounts still available from shared file.
