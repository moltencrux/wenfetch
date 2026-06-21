# 中文閱讀推薦 zh-recommender

Recommends Chinese news articles based on your vocabulary level.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run migrations and create a superuser
python manage.py migrate
python manage.py createsuperuser

# Load your frequency table (one-time)
python manage.py import_freq --file data/freq.tsv

# Scrape articles (run periodically via cron)
python scraper/scrape.py --articles data/articles

# Segment and index articles into the database
python manage.py import_tokens

# Start the dev server
python manage.py runserver
```

## Cron setup (example)

```cron
# Scrape and index nightly at 2am
0 2 * * * cd /path/to/zh-recommender && \
  .venv/bin/python scraper/scrape.py --articles data/articles && \
  .venv/bin/python manage.py import_tokens \
  >> data/cron.log 2>&1
```

## Production deployment

```bash
cp .env.example .env   # edit DJANGO_SECRET_KEY and ALLOWED_HOSTS
cd infra
docker compose up -d

# First-time setup inside the container
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py import_freq --file data/freq.tsv
docker compose exec web python manage.py import_tokens
```

## Environment variables (production)

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Long random string, keep secret |
| `ALLOWED_HOSTS` | Comma-separated hostnames, e.g. `example.com,www.example.com` |
