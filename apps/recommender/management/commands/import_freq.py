"""
Import a word frequency table into the database.

Usage:
    manage.py import_freq --file data/freq.tsv
    manage.py import_freq --file data/freq.tsv --clear
"""

from django.core.management.base import BaseCommand, CommandError
from apps.recommender.models import FreqEntry


class Command(BaseCommand):
    help = "Import a word frequency table (word\\tfreq per line) into the database."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to freq.tsv")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing entries before importing.",
        )

    def handle(self, *args, **options):
        path = options["file"]

        if options["clear"]:
            count = FreqEntry.objects.count()
            FreqEntry.objects.all().delete()
            self.stdout.write(f"Cleared {count} existing entries.")

        entries = []
        skipped = 0
        try:
            with open(path, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.rstrip("\n")
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) < 2:
                        self.stderr.write(
                            f"Line {lineno} malformed, skipping: {line!r}"
                        )
                        skipped += 1
                        continue
                    try:
                        entries.append(
                            FreqEntry(word=parts[0], frequency=int(parts[1]))
                        )
                    except ValueError:
                        self.stderr.write(f"Line {lineno} non-integer freq, skipping.")
                        skipped += 1
        except FileNotFoundError:
            raise CommandError(f"File not found: {path}")

        FreqEntry.objects.bulk_create(entries, ignore_conflicts=True, batch_size=5000)
        self.stdout.write(
            self.style.SUCCESS(f"Imported {len(entries)} entries ({skipped} skipped).")
        )
