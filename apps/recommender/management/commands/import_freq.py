"""
Import a word frequency table into the database.

Usage:
    manage.py import_freq --file data/freq.tsv
    manage.py import_freq --file data/freq.tsv --clear
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from apps.recommender.models import FreqEntry


class Command(BaseCommand):
    help = "Import word frequency table (auto-detects CSV/TSV and header)."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to frequency file")
        parser.add_argument("--clear", action="store_true", help="Clear existing data first")

    def handle(self, *args, **options):
        path = Path(options["file"]).resolve()

        if options["clear"]:
            count = FreqEntry.objects.count()
            FreqEntry.objects.all().delete()
            self.stdout.write(f"Cleared {count} existing entries.")

        # Detect format
        with open(path, encoding="utf-8") as f:
            sample = f.read(8192)

        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample)
            has_header = sniffer.has_header(sample)
        except csv.Error:
            dialect = csv.get_dialect('excel-tab')
            has_header = True  # conservative

        self.stdout.write(f"Detected delimiter: {dialect.delimiter!r} "
                         f"({'CSV' if dialect.delimiter == ',' else 'TSV'})")

        entries = []
        skipped = 0
        imported = 0
        batch_size = 5000

        with open(path, encoding="utf-8") as f:
            reader = csv.reader(f, dialect=dialect)

            if has_header:
                header = next(reader, None)
                self.stdout.write(f"Skipped header: {header}")

            for row in reader:
                if len(row) < 2:
                    skipped += 1
                    continue

                word = row[0].strip()
                if not word or word.startswith("#"):
                    skipped += 1
                    continue

                try:
                    freq = int(row[1].strip().replace(",", ""))
                    entries.append(FreqEntry(word=word, frequency=freq))
                    imported += 1
                except ValueError:
                    skipped += 1
                    continue

                if len(entries) >= batch_size:
                    FreqEntry.objects.bulk_create(entries, ignore_conflicts=True)
                    entries.clear()

        if entries:
            FreqEntry.objects.bulk_create(entries, ignore_conflicts=True)

        self.stdout.write(
            self.style.SUCCESS(f"Imported {imported} entries ({skipped} skipped).")
        )
