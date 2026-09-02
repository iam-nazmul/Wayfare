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
    """Split on statement terminators, ignoring ``;`` inside comments and quoted literals."""
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0

    while index < len(sql):
        char = sql[index]

        if quote is not None:
            current.append(char)
            if char == "\\" and index + 1 < len(sql):
                current.append(sql[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
        elif char in "'\"`":
            quote = char
            current.append(char)
            index += 1
        elif sql.startswith("--", index):
            newline = sql.find("\n", index)
            index = len(sql) if newline == -1 else newline
        elif sql.startswith("/*", index):
            close = sql.find("*/", index + 2)
            index = len(sql) if close == -1 else close + 2
        elif char == ";":
            statements.append("".join(current))
            current = []
            index += 1
        else:
            current.append(char)
            index += 1

    statements.append("".join(current))
    return [statement.strip() for statement in statements if statement.strip()]
