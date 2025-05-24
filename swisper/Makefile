.PHONY: dev stop index-docs clean-db clean-artifacts logs build

dev:
	@echo "Starting services with Docker Compose..."
	docker-compose up --build -d # -d for detached mode

stop:
	@echo "Stopping Docker Compose services..."
	docker-compose down

# This assumes your gateway service is named 'gateway' in docker-compose.yml
# and your sample documents are in 'docs/' relative to the swisper/ root (mounted as /app/docs in container)
index-docs:
	@echo "Indexing documents from ./docs/ into Haystack Document Store via Docker..."
	docker-compose exec gateway python haystack_pipeline/indexer.py docs/*.txt
	@echo "Indexing complete. Document store count might be visible in gateway logs if indexer logs there."

clean-db:
	@echo "Removing session database..."
	# This attempts to remove files that shelve might create.
	# The exact filenames can vary slightly depending on the shelve backend used by the OS.
	rm -f orchestrator_sessions.db orchestrator_sessions.db.bak orchestrator_sessions.db.dat orchestrator_sessions.db.dir orchestrator_sessions.db.db
	@echo "Note: If shelve uses a different backend, other files might need manual removal from the 'swisper/' directory (or mounted volume location)."

clean-artifacts:
	@echo "Removing contract artifacts..."
	rm -rf tmp/contracts/*
	@echo "Contract artifacts removed."

# A target to check logs of the gateway
logs:
	docker-compose logs -f gateway

# A target to rebuild images without starting services
build:
	docker-compose build
