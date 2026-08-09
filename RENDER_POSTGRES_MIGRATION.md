# Render Postgres Migration

This project now supports two database modes:

- Local development without `DATABASE_URL`: SQLite (`db.sqlite3`)
- Render or any environment with `DATABASE_URL`: PostgreSQL

## 1. Provision Postgres on Render

If you deploy from `render.yaml`, sync the blueprint so Render creates the `afyorabe-db` database and injects its `connectionString` into `DATABASE_URL` for the web service.

If you manage services manually in the Render dashboard, create a PostgreSQL database and add its connection string to the web service as `DATABASE_URL`.

## 2. Back Up the Current SQLite Data

From the project root:

```bash
source venv/bin/activate
cp db.sqlite3 db.sqlite3.backup
python manage.py dumpdata \
  --exclude contenttypes \
  --exclude auth.permission \
  --exclude admin.logentry \
  --natural-foreign \
  --natural-primary \
  --indent 2 > data-migration.json
```

## 3. Load the Data into Postgres

Use the external connection string from your Render Postgres instance for the one-time import from your machine.

```bash
source venv/bin/activate
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:PORT/DATABASE?sslmode=require'
python manage.py migrate --noinput
python manage.py loaddata data-migration.json
```

## 4. Verify the Imported Data

```bash
python manage.py shell -c "from django.contrib.auth import get_user_model; from patients.models import Patient; print('users=', get_user_model().objects.count(), 'patients=', Patient.objects.count())"
```

## 5. Redeploy the Render Web Service

After the data is in Postgres, trigger a Render deploy. The service will keep using Postgres because Render supplies `DATABASE_URL`, and future migrations will run automatically via `preDeployCommand`.

## Notes

- Keep `db.sqlite3` until you confirm production data is present in Postgres.
- `loaddata` preserves hashed passwords, so existing users can keep signing in.
- If you already created a superuser directly in Postgres before import and get duplicate-user errors, drop that user first or rebuild the Postgres database and re-run the import.
