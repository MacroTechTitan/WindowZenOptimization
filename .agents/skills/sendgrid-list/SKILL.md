---
name: sendgrid-list
description: Add contacts to a SendGrid marketing list from a Python/Flask app. Use when the user wants to sync email addresses to a SendGrid audience/list, wire up a registration flow to SendGrid, or add SendGrid contact list syncing to any Python backend.
---

# SendGrid List Sync (Python/Flask)

Wires up automatic contact syncing to a SendGrid marketing list whenever a user submits their email. Uses the SendGrid Marketing Contacts API — no SDK required, just `urllib`.

## Credentials Needed

| Secret/Env Var | Where to get it | How to store |
|---|---|---|
| `SENDGRID_API_KEY` | SendGrid → Settings → API Keys (needs Marketing read/write) | Replit secret |
| `SENDGRID_LIST_ID` | SendGrid → Marketing → Contacts → your list → ID in URL | Replit shared env var via `setEnvVars` |

**This project's values:**
- `SENDGRID_LIST_ID` = `1fd9b188-b87e-4583-bc37-304f1ac142cc`
- `SENDGRID_API_KEY` already stored as a secret

## Check Existing Secrets First

```javascript
const result = await viewEnvVars({ type: "secret" });
console.log(result.secrets); // check for SENDGRID_API_KEY

await setEnvVars({ values: { SENDGRID_LIST_ID: "<your-list-id>" } });
```

## Python Function (drop into app.py)

Requires only stdlib — no extra packages.

```python
def add_to_sendgrid_list(email):
    api_key = os.environ.get("SENDGRID_API_KEY")
    list_id = os.environ.get("SENDGRID_LIST_ID")
    if not api_key:
        log_activity("SendGrid sync skipped — no API key", "WARN")
        return
    payload = {"contacts": [{"email": email}]}
    if list_id:
        payload["list_ids"] = [list_id]
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/marketing/contacts",
            data=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            log_activity(f"SendGrid contact added: {email} (status {resp.status})", "SUCCESS")
    except Exception as e:
        log_activity(f"SendGrid sync failed for {email}: {e}", "WARN")
```

> Note: `log_activity` is project-specific. Replace with `print`, `logging.info`, etc. if not present.

## Where to Call It

Call after a successful registration save — never block the user response on it:

```python
ok = send_verification_email(email, token)
if not ok:
    return jsonify({"error": "Failed to send email."}), 500
add_to_sendgrid_list(email)   # fire-and-forget, failures only warn
return jsonify({"ok": True, "message": "Verification email sent!"})
```

## API Details

- **Endpoint**: `PUT https://api.sendgrid.com/v3/marketing/contacts`
- **Auth**: `Authorization: Bearer <SENDGRID_API_KEY>`
- **Body**:
  ```json
  {
    "list_ids": ["<your-list-id>"],
    "contacts": [{ "email": "user@example.com" }]
  }
  ```
- **Notes**: This is an async upsert — SendGrid processes contacts in batches. The response is `202 Accepted`, not an immediate confirmation. You can also pass `first_name`, `last_name`, and custom fields inside each contact object.

## Imports Required

Make sure these are at the top of your Python file:

```python
import os
import json
import urllib.request
```

## Design Decisions

- Failures log a WARN but never raise — sync errors should not block the user flow
- `list_ids` is optional; omitting it adds the contact to general contacts without a list
- Re-submitting the same email is safe — SendGrid upserts, no duplicates
