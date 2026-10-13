# SHADOW MCQ Platform — cloud-backed starter

SHADOW is a Flask MCQ test platform with email OTP creator sign-in, public student test links, server-side PostgreSQL storage, result CSV exports, and an owner-only platform analytics page.

## Requirements

- Python 3.11 or 3.12
- A Supabase project
- A server/host that can reach Supabase PostgreSQL
- Email delivery configured in Supabase Auth

## 1. Create the Supabase project

1. Create a project at https://supabase.com/.
2. In **Authentication → Providers → Email**, enable email sign-in. Configure email OTP/magic-link delivery to use an OTP code that can be entered on the verification page. Supabase's email template should include `{{ .Token }}` if you want a numeric OTP.
3. Find the project URL and publishable/anon key in **Project Settings → API**.
4. Find the PostgreSQL connection string in **Project Settings → Database → Connection string**. Use the URI format and add `?sslmode=require` (or keep the SSL parameter supplied by Supabase). URL-encode special characters in the database password.
5. Open **SQL Editor** in Supabase and run the complete contents of `schema.sql`.

## 2. Configure environment variables on Windows PowerShell

Open PowerShell in this project folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

$env:FLASK_SECRET_KEY = "replace-this-with-a-long-random-secret"
$env:SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
$env:SUPABASE_ANON_KEY = "YOUR_SUPABASE_PUBLISHABLE_OR_ANON_KEY"
$env:DATABASE_URL = "YOUR_SUPABASE_POSTGRES_CONNECTION_URI"
$env:ADMIN_EMAILS = "owner@example.com"
python app.py
```

Then open http://127.0.0.1:5000.

Do not commit actual secrets or your database password to GitHub. For deployment, set these values in your hosting provider's environment-variable settings. `ADMIN_EMAILS` can contain multiple comma-separated owner email addresses. Only those emails can open `/admin`.

## How it works

- Creator accounts use Supabase email OTP; no platform password is collected.
- Students open a published shared link and enter their name and candidate/roll number. They do not need a SHADOW account.
- Tests, questions, options, attempts, responses, security events, and platform event logs are stored in Supabase PostgreSQL, so creator data is not tied to a single laptop.
- Creators only see and manage their own tests. The owner analytics dashboard is restricted by the `ADMIN_EMAILS` allowlist.
- Test results can be exported to CSV; owner-level platform events can also be exported to CSV.

## Important limitations

This is a working starter/MVP, not a certified proctoring system. Browser JavaScript can detect some events such as switching away from the exam tab, blur, or leaving fullscreen, but it cannot reliably block OS screenshots, another phone, external AI apps, other browsers, or a second physical device. These controls can also generate false positives. For high-stakes exams, use a managed exam browser and managed devices, and conduct security testing before deployment.

The browser-side exam timer is a user-interface timer; before using this for high-stakes exams, add authoritative server-side deadline enforcement and comprehensive tests. Configure Supabase email delivery/rate limits and your hosting platform before production use.
