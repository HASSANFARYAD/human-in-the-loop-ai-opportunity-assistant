.PHONY: setup secrets smoke docker-up docker-down backup restore clean

setup:
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	mkdir -p data logs backups

secrets:
	python scripts/generate_secrets.py

smoke:
	python scripts/smoke_test.py

docker-up:
	docker compose up --build

docker-down:
	docker compose down

backup:
	python scripts/backup_sqlite.py --db $${APP_DB_PATH:-data/job_assistant.sqlite3} --out-dir backups

restore:
	@test -n "$(BACKUP)" || (echo "Usage: make restore BACKUP=backups/file.sqlite3" && exit 1)
	python scripts/restore_sqlite.py "$(BACKUP)" --db $${APP_DB_PATH:-data/job_assistant.sqlite3}

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
