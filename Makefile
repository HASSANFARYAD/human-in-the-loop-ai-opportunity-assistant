.PHONY: setup secrets smoke docker-up docker-down backup restore clean

setup:
	python -m pip install --upgrade pip
	pip install -r backend/requirements.txt
	mkdir -p backend/data backend/logs backend/backups

secrets:
	python backend/scripts/generate_secrets.py

smoke:
	cd backend && python -m scripts.smoke_test

docker-up:
	docker compose --env-file backend/.env up --build

docker-down:
	docker compose down

backup:
	python backend/scripts/backup_sqlite.py --db $${APP_DB_PATH:-backend/data/job_assistant.sqlite3} --out-dir backend/backups

restore:
	@test -n "$(BACKUP)" || (echo "Usage: make restore BACKUP=backend/backups/file.sqlite3" && exit 1)
	python backend/scripts/restore_sqlite.py "$(BACKUP)" --db $${APP_DB_PATH:-backend/data/job_assistant.sqlite3}

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
