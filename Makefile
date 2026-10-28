# One-command workflows. See CLAUDE.md.
.PHONY: check test lint tools fetch site serve
PORT ?= 8611

check: test lint ## everything: unit tests, compile check, actionlint (+shellcheck) on the workflow and scripts
	@echo "check: OK"

test:
	python3 -m py_compile fetch_jobs.py
	python3 -m unittest discover -s tests

tools:
	@scripts/tools.sh

lint: tools
	.tools/actionlint -shellcheck .tools/shellcheck .github/workflows/refresh.yml
	.tools/shellcheck scripts/*.sh

fetch: ## refresh docs/jobs.json + seen.json locally (both gitignored)
	python3 fetch_jobs.py

site: ## build the Pages artifact into _site/ exactly as CI does (state in .state/)
	scripts/build_site.sh .state _site

serve: ## serve _site/ locally
	python3 -m http.server --bind 127.0.0.1 --directory _site $(PORT)
