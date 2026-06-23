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

seed:
	python backend/scripts/seed_data.py

backup:
	python -c "from job_assistant.backup import run_backup; run_backup()"

restore:
	@echo "Restore from MongoDB backup: mongoimport"
	@echo "See: https://www.mongodb.com/docs/database-tools/mongoimport/"

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
