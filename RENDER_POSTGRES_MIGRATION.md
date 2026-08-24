# Supabase Primary and Render Backup

This deployment uses Supabase PostgreSQL as the application primary and Render
PostgreSQL as a one-way disaster-recovery backup. The application reads and
writes **only** Supabase. A scheduled sync replaces the Render database with a
consistent snapshot from Supabase.

This is intentionally not active-active replication: two independent Postgres
services cannot safely accept the same writes without conflict handling and a
replication system. Do not point the deployed web service at the Render URL.

## Required environment variables

Set these in Render and locally when running the sync:

```bash
SUPABASE_DATABASE_URL='postgresql://...'
RENDER_DATABASE_URL='postgresql://...'
```

Use Supabase's direct PostgreSQL connection string, including its SSL options.
`DATABASE_URL` is accepted as a backwards-compatible primary fallback, but new
deployments should use `SUPABASE_DATABASE_URL`.

## Initial setup

1. Create the Render PostgreSQL database from `render.yaml`.
2. Set `SUPABASE_DATABASE_URL` on the Render web service and on the backup job.
3. Set `RENDER_DATABASE_URL` from the Render database's internal connection
   string.
4. Run migrations against Supabase only:

```bash
python manage.py migrate --noinput
```

5. Prepare the backup schema, then create the first backup:

```bash
python manage.py migrate --database=backup --noinput
python manage.py sync_render_backup --noinput
```

Run that command from a Render Cron Job or another trusted scheduler (for
example, hourly). It is safe to rerun, but it **replaces data in every table in
the Render backup**. Before syncing after a model migration, run `migrate
--database=backup` so the schemas match. Keep the Render database private and
never use it for app writes.

## Restoring after a Supabase incident

Stop application writes, change `SUPABASE_DATABASE_URL` to the restored Render
database URL, deploy, and then establish a new backup target. Verify the
application before reopening writes. This controlled failover avoids split-brain
data.
