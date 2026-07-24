# 中文閱讀推薦 wenfetch

A Django app that recommends Chinese articles based on your vocabulary level.


## Quick User Guide

### 1. Access the App
- Deploy or run the Django app (see Development/Production setup below).
- Visit the site in your browser (e.g., http://localhost:8000).

### 2. Create an Account / Login
- Register a new account or log in with existing credentials.

### 3. Manage Your Vocabulary Lists
- Go to Vocab Lists section.
- Create a new list.
- Add words:
  - Paste text containing Chinese words, 1 word per line.
  - Or upload a text file with vocabulary that can be exported from an SRS app like Pleco or Anki.
- The app will extract and add unique words to your list.

### 4. Get Recommendations
- Navigate to Recommendations.
- Select one of your vocab lists.
- Optionally filter by source.
- Choose heuristic (e.g., avg) and number of articles.
- Submit to get personalized article recommendations based on word frequency/new words.

### 5. Read Articles
- Click on recommended articles to read full content.

## Ranking Heuristic Explanations
This is an explanation of the way articles are scored for each heuristic method

- **Average frequency** - Ranks articles based on the average frequency of new vocabulary (e.g. vocabuulary not in your selected vocabulary list)
  * This is probably the preferred mode as it will tend to recommend articles with a reasonable amount of new vocabulary that is most useful to the user.

- **Total frequency** - Ranks articles based on the total frequency of new vocabulary they contain
  - This mode will tend to select articles with the most new words and will likely be overwheliming to all but very advanced learners.

## Development setup

```bash
git clone https://github.com/moltencrux/wenfetch
cd wenfetch

# git checkout dev/testing
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Compile translation messages
python manage.py compilemessages

# Run migrations and create a superuser
python manage.py migrate
python manage.py createsuperuser

# You could also substitute one of the following tables:
# https://bcc.blcu.edu.cn/api/datasets/dialogue_word_freq.txt/download
# https://bcc.blcu.edu.cn/api/datasets/multi_domain_total_word_freq.txt/download
# https://bcc.blcu.edu.cn/api/datasets/literature_word_freq.txt/download
# https://bcc.blcu.edu.cn/api/datasets/modern_chinese_word_freq.txt/download
# https://bcc.blcu.edu.cn/api/datasets/classical_chinese_word_freq.txt/downloa 

# Download frequency tables
funzip <(curl \
  https://bcc.blcu.edu.cn/api/datasets/news_total_word_freq.txt/download) \
  > data/news_total_word_freq.txt

# Import frequency data
python manage.py import_freq --file data/news_total_word_freq.txt

# Get a list of valid dictionary words
curl -L \
  https://github.com/g0v/moedict-data/raw/refs/heads/master/dict-revised_bkup.json.xz \
  | xzcat | jq -r '.[].title' > data/moe_words.txt

# Run the scraper to download article text
python scrape.py --depth 5 --since $(date -d '2 weeks ago' +%Y-%m-%d) \
  --limit 70 --max-stale 30

# Import segmented words from downloaded articles. This should be run
# after each time articles are scraped
python manage.py import_tokens --dict data/moe_words.txt

# Start the dev server
python manage.py runserver localhost:8080
```

### Cron setup (example)

```cron
# Scrape and index nightly at 2am
0 2 * * * cd /path/to/zh-recommender && \
  .venv/bin/python scraper/scrape.py --articles data/articles && \
  .venv/bin/python manage.py import_tokens \
  >> data/cron.log 2>&1
```

### Updating translations
```bash
# Sync up translations after changes any to interface messages (usually
# in templates) so that translations can be updated
python manage.py makemessages -l zh-hant -l zh-hans -l en -a

# Subsequently, update *.po files for all translations and run
python manage.py compilemessages
```

### Using docker-compose with podman
```bash
# Standard podman-compose does not support docker-compose config
# command, which # is used by our compose setup. But docker-compose
# can be used as a provider for podman-config.

export DOCKER_HOST=unix:///run/user/$(id -u)/podman/podman.sock

# Now you can bring up services using: podman up
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


### Environment variables (production)

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Long random string, keep secret |
| `ALLOWED_HOSTS` | Comma-separated hostnames, e.g. `example.com,www.example.com` |

### CronTab entries to run through docker/podman compose
```
# Scrape nightly at 2am
0 2 * * * cd /home/agc/dev/wenfetch && \
  .venv/bin/python scrape.py --articles data/articles \
  >> data/logs/scrape.log 2>&1

# Segment and index after scraping
30 2 * * * cd /home/agc/dev/wenfetch && \
  podman-compose -f infra/docker-compose.yml exec -T web \
  python manage.py import_tokens --dict data/moe_words.txt \
  >> data/logs/import.log 2>&1
```

