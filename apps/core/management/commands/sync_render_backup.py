"""Synchronize the Supabase PostgreSQL primary to the Render backup."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

try:
    from psycopg import sql
except ImportError:  # pragma: no cover - Django's PostgreSQL backend requires it
    sql = None


class Command(BaseCommand):
    help = (
        'Replace the Render backup data with a consistent snapshot from the '
        'Supabase primary. The backup must not receive application writes.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--noinput', action='store_true', help='Skip the confirmation prompt.')

    def handle(self, *args, **options):
        self._validate_databases()
        if not options['noinput']:
            confirmation = input(
                'This replaces all Render backup data with the Supabase primary. Continue? [y/N] '
            )
            if confirmation.lower() not in {'y', 'yes'}:
                self.stdout.write('Backup sync cancelled.')
                return

        source = connections['default']
        target = connections['backup']
        tables = self._tables(source)
        self._ensure_matching_schema(source, target, tables)

        # A repeatable-read source transaction provides one primary snapshot.
        # The target transaction rolls back if any table copy fails.
        with transaction.atomic(using='default'), transaction.atomic(using='backup'):
            with source.cursor() as source_cursor, target.cursor() as target_cursor:
                source_cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                target_cursor.execute('SET CONSTRAINTS ALL DEFERRED')
                self._truncate(target_cursor, tables)
                for table in tables:
                    self._copy_table(source_cursor, target_cursor, table)
                self._reset_sequences(target_cursor, tables)

        self.stdout.write(self.style.SUCCESS('Render backup synchronized successfully.'))

    @staticmethod
    def _validate_databases():
        if sql is None:
            raise CommandError('psycopg is required to synchronize PostgreSQL databases.')
        if 'backup' not in settings.DATABASES:
            raise CommandError('RENDER_DATABASE_URL is not configured. Set it before syncing the backup.')
        for alias in ('default', 'backup'):
            if settings.DATABASES[alias]['ENGINE'] != 'django.db.backends.postgresql':
                raise CommandError(f'The {alias} database must be PostgreSQL.')

    @staticmethod
    def _tables(connection):
        with connection.cursor() as cursor:
            cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            return [row[0] for row in cursor.fetchall()]

    def _ensure_matching_schema(self, source, target, source_tables):
        target_tables = self._tables(target)
        if source_tables != target_tables:
            raise CommandError(
                'The Render backup schema differs from Supabase. Run '
                '`python manage.py migrate --database=backup --noinput` first.'
            )
        for table in source_tables:
            if self._columns(source, table) != self._columns(target, table):
                raise CommandError(
                    f'The schema for public.{table} differs on Render. Run migrations on the backup first.'
                )

    @staticmethod
    def _columns(connection, table):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name, data_type, udt_name, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
                """,
                [table],
            )
            return cursor.fetchall()

    @staticmethod
    def _truncate(cursor, tables):
        if not tables:
            return
        identifiers = sql.SQL(', ').join(
            sql.SQL('public.{}').format(sql.Identifier(table)) for table in tables
        )
        cursor.execute(sql.SQL('TRUNCATE TABLE {} RESTART IDENTITY CASCADE').format(identifiers))

    @staticmethod
    def _copy_table(source_cursor, target_cursor, table):
        source_statement = sql.SQL('COPY public.{} TO STDOUT WITH (FORMAT BINARY)').format(
            sql.Identifier(table)
        )
        target_statement = sql.SQL('COPY public.{} FROM STDIN WITH (FORMAT BINARY)').format(
            sql.Identifier(table)
        )
        with source_cursor.copy(source_statement) as source_copy, target_cursor.copy(target_statement) as target_copy:
            for chunk in source_copy:
                target_copy.write(chunk)

    def _reset_sequences(self, cursor, tables):
        for table in tables:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                  AND (column_default LIKE 'nextval(%%' OR is_identity = 'YES')
                """,
                [table],
            )
            for (column,) in cursor.fetchall():
                relation = f'public.{table}'
                query = sql.SQL(
                    'SELECT setval(pg_get_serial_sequence(%s, %s), '
                    'COALESCE(MAX({column}), 1), COUNT({column}) > 0) '
                    'FROM public.{table}'
                ).format(column=sql.Identifier(column), table=sql.Identifier(table))
                cursor.execute(query, [relation, column])
