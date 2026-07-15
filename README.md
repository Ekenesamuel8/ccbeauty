# CCbeauty

CCbeauty is a Django monolith for a Nigerian beauty-products store. It uses Django templates for the storefront, a session-backed cart, Django accounts and profiles, and Paystack for payments.

This Phase 0 foundation keeps the existing page design and commerce behavior unchanged. Payment and order behavior is known to need redesign, but that work belongs to a later phase.

## Requirements

- Python 3.11 (the repository's existing environment uses Python 3.11.4)
- Windows PowerShell commands are shown below
- PostgreSQL and Cloudflare R2 are needed only for production

`ecommerce/requirements.txt` is the authoritative dependency manifest. Some currently unused packages (including the unrouted REST/JWT stack and disabled reCAPTCHA integration) are intentionally retained until a later dependency-cleanup phase.

## Local setup on Windows

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\ecommerce\requirements.txt
Copy-Item .\ecommerce\.env.example .\ecommerce\.env
```

Open `ecommerce/.env` and keep `DJANGO_ENV=development`.

Development is also the default when `DJANGO_ENV` is absent. It uses:

- `DEBUG=True`
- local SQLite at `ecommerce/db.sqlite3` unless `SQLITE_PATH` is supplied
- local uploaded media in `ecommerce/media/`
- local static source files in `ecommerce/static/`
- console email unless `DEVELOPMENT_USE_SMTP=true`
- no Supabase or Cloudflare R2 connection

The development secret-key fallback is deliberately insecure and must never be used in production.

## Database and catalog

Move into the Django application directory before management commands:

```powershell
Set-Location .\ecommerce
python manage.py migrate
```

The repository currently has a historical, populated `db.sqlite3`. Treat it as local/historical data, not as a production database. It may contain account, session, order and payment records and is already present in Git history. The new ignore rules do not remove already tracked files or rewrite history.

For a new empty development database, set `SQLITE_PATH` in `.env` to a different local filename, run migrations, and then load the catalog fixtures in dependency order:

```powershell
python manage.py loaddata category.json
python manage.py loaddata products.json
```

Never load these fixtures blindly into production. Review the target database and fixture contents first.

## Run the application

From `ecommerce/`:

```powershell
python manage.py check
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Development email is printed to the terminal. Set `DEVELOPMENT_USE_SMTP=true` only when intentionally testing SMTP with non-production credentials.

## Checks and tests

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Django's test runner creates an isolated temporary SQLite test database. Tests do not use Supabase, R2, or real email delivery.

## Environment selection

The default settings module remains `ecommerce.settings`, so `manage.py`, WSGI and ASGI continue to work without command changes. `ecommerce.settings` selects an environment using `DJANGO_ENV`:

- `development`, `dev`, or `local` loads `ecommerce.settings.development`.
- `production` or `prod` loads `ecommerce.settings.production`.
- Any other value fails immediately.

The `.env` file is loaded before selection. Use `.env.example` only as a variable-name template; do not commit `.env` or real credentials.

## Production configuration

Production requires explicit values for:

- `SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS` (wildcards are rejected)
- PostgreSQL `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and `DB_HOST`
- Paystack public and secret keys
- SMTP user and password
- all required Cloudflare R2 variables shown in `.env.example`

The existing `SUPABASE_DB_*` names and legacy `NAME`, `USER`, `PASSWORD`, `HOST`, and `PORT` names remain supported, but `DB_*` is preferred. Existing `EMAIL_HOST_USERS` and the legacy password stored under `EMAIL_HOST` are also accepted; new environments should use `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, and `SMTP_HOST`.

Before deploying, verify that the reverse proxy sends `X-Forwarded-Proto`, review HSTS values for the actual domains, run the deployment check, apply migrations, and collect static files:

```powershell
$env:DJANGO_ENV = "production"
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
```

Production static files are collected into `ecommerce/staticfiles/` and must be served by the deployment platform or web server. Uploaded media uses Cloudflare R2.

## Phase boundary

Phase 0 does not change models, migrations, templates, checkout, order creation, or Paystack behavior. The current payment/order association and verification flow should be redesigned and tested in a later phase before accepting real customer payments.
