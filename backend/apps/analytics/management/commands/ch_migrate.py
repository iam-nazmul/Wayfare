from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.analytics.clickhouse import get_client

MIGRATIONS_DIR = Path(settings.BASE_DIR) / "clickhouse" / "migrations"

TRACKING_TABLE = """
CREATE TABLE IF NOT EXISTS {db}.schema_migrations (
    name String,
    applied_at DateTime DEFAULT now()
) ENGINE = MergeTree ORDER BY name
"""


class Command(BaseCommand):
    help = "Apply ClickHouse migrations from clickhouse/migrations/, tracked in schema_migrations."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options) -> None:
        db = settings.CLICKHOUSE["DATABASE"]
        client = get_client()

        client.command(f"CREATE DATABASE IF NOT EXISTS {db}")
        client.command(TRACKING_TABLE.format(db=db))

        applied = {
            row[0]
            for row in client.query(f"SELECT name FROM {db}.schema_migrations").result_rows
        }

        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not files:
            self.stdout.write("no ClickHouse migrations found")
            return

        pending = [path for path in files if path.name not in applied]
        if not pending:
            self.stdout.write(self.style.SUCCESS(f"ClickHouse up to date ({len(applied)} applied)"))
            return

        for path in pending:
            self.stdout.write(f"applying {path.name}")
            if options["dry_run"]:
                continue
            for statement in _statements(path.read_text()):
                client.command(statement)
            client.insert(
                f"{db}.schema_migrations", [[path.name]], column_names=["name"]
            )

        self.stdout.write(self.style.SUCCESS(f"applied {len(pending)} ClickHouse migration(s)"))


def _statements(sql: str) -> list[str]:
    statements = []
    for chunk in sql.split(";"):
        cleaned = "\n".join(
            line for line in chunk.splitlines() if not line.strip().startswith("--")
        ).strip()
        if cleaned:
            statements.append(cleaned)
    return statements
