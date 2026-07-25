"""
Import word and/or character frequency tables.

Usage:
    manage.py import_freq --word-file data/news_total_word_freq.txt
    manage.py import_freq --char-file data/char_freq.txt
    manage.py import_freq --word-file ... --char-file ... --clear
"""

import csv
from itertools import batched
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from apps.recommender.models import FreqEntry, CharFreqEntry
from apps.recommender.utils import process_vocab_entry_on_add


class Command(BaseCommand):
    help = "Import word and/or character frequency tables (auto-detects CSV/TSV)."

    def add_arguments(self, parser):
        parser.add_argument("--word-file", default=None,
                            help="Path to word frequency file")
        parser.add_argument("--char-file", default=None,
                            help="Path to character frequency file")
        parser.add_argument("--clear", action="store_true",
                            help="Clear existing data first")


    def handle(self, *args, **options):
        if options["clear"]:
            word_count = FreqEntry.objects.count()
            char_count = CharFreqEntry.objects.count()
            FreqEntry.objects.all().delete()
            CharFreqEntry.objects.all().delete()
            self.stdout.write(
                f"Cleared {word_count} word and {char_count} character entries."
            )

        def iter_freq_rows(path: Path):
            with open(path, encoding="utf-8") as f:
                sample = f.read(8192)

            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(sample)
                has_header = sniffer.has_header(sample)
            except csv.Error:
                dialect = csv.get_dialect("excel-tab")
                has_header = True

            self.stdout.write(
                f"Detected delimiter: {dialect.delimiter!r} "
                f"({'CSV' if dialect.delimiter == ',' else 'TSV'})"
            )

            with open(path, encoding="utf-8") as f:
                reader = csv.reader(f, dialect=dialect)
                if has_header:
                    header = next(reader, None)
                    self.stdout.write(f"Skipped header: {header}")

                for row in reader:
                    if len(row) < 2:
                        continue
                    entry = row[0].strip()
                    if not entry or entry.startswith("#"):
                        continue
                    try:
                        freq = int(row[1].strip().replace(",", ""))
                    except ValueError:
                        continue
                    yield entry, freq

        def load(path, model, field, label):
            path = Path(path).resolve()
            if not path.exists():
                raise CommandError(f"{label} file not found: {path}")

            imported = skipped = 0
            batch = []

            for raw, freq in iter_freq_rows(path):
                if label == "word":
                    entry = process_vocab_entry_on_add(raw)
                else:  # character
                    entry = raw.strip()
                    if len(entry) != 1:
                        skipped += 1
                        continue

                if not entry:
                    skipped += 1
                    continue

                batch.append(model(**{field: entry, "frequency": freq}))
                imported += 1

                if len(batch) >= 5000:
                    model.objects.bulk_create(batch, ignore_conflicts=True)
                    batch.clear()

            if batch:
                model.objects.bulk_create(batch, ignore_conflicts=True)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Imported {imported} {label} entries ({skipped} skipped)."
                )
            )

        if options["word_file"]:
            load(options["word_file"], FreqEntry, "word", "word")
        if options["char_file"]:
            load(options["char_file"], CharFreqEntry, "char", "character")
