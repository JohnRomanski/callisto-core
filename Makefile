.DEFAULT_GOAL := help

RUN := uv run
UNIT_TESTS := callisto_core/ --ignore=callisto_core/tests/delivery/test_frontend.py --ignore=callisto_core/wizard_builder/tests/test_frontend.py

help:
	@perl -nle'print $& if m{^[a-zA-Z_-]+:.*?## .*$$}' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

clean: ## remove build artifacts and caches
	rm -fr build/ dist/ *.egg-info
	rm -rf *.sqlite3
	rm -rf callisto_core/wizard_builder/tests/screendumps/
	rm -rf callisto_core/wizard_builder/tests/staticfiles/
	find callisto_core -type d -name "__pycache__" -exec rm -rf {} +

install: ## install the locked dev environment
	uv sync --locked

lint: ## format and autofix with ruff
	$(RUN) ruff format .
	$(RUN) ruff check --fix .

test-lint: ## check formatting and lint with ruff
	$(RUN) ruff format --check .
	$(RUN) ruff check .

test-suite: ## run django checks and the unit tests
	$(RUN) python manage.py check
	$(RUN) python manage.py makemigrations --check --dry-run
	$(RUN) pytest -vls $(UNIT_TESTS)

test-integrated: ## run the selenium frontend tests
	$(RUN) pytest -vls callisto_core/tests/delivery/test_frontend.py

test-fast: ## runs the test suite, with fast failures and a re-used database
	LOG_LEVEL=INFO $(RUN) pytest -vls --maxfail=1 --ff --reuse-db $(UNIT_TESTS)

test: ## run the linters and the test suite
	make test-lint
	make test-suite
	make test-integrated

build: clean ## build the sdist and wheel into dist/
	uv build

osx-install:
	brew install git uv postgres chromedriver gnupg

app-setup: ## setup the test application environment
	- $(RUN) python manage.py flush --noinput
	$(RUN) python manage.py migrate --noinput --database default
	$(RUN) python manage.py create_admins
	$(RUN) python manage.py setup_sites
	$(RUN) python manage.py loaddata wizard_builder_data
	$(RUN) python manage.py loaddata callisto_core_notification_data
	$(RUN) python manage.py demo_user

dev-setup:
	- dropdb callisto-core
	- createdb callisto-core
	- make osx-install
	make install
	$(RUN) pre-commit install
	make app-setup

wizard-update-fixture: ## update fixture with migrations added on the local branch
	- dropdb callisto-core
	createdb callisto-core
	git checkout master
	- $(RUN) python manage.py migrate
	- $(RUN) python manage.py loaddata callisto_core/wizard_builder/fixtures/wizard_builder_data.json -i
	git checkout @{-1}
	$(RUN) python manage.py migrate
	$(RUN) python manage.py dumpdata wizard_builder -o callisto_core/wizard_builder/fixtures/wizard_builder_data.json
	npx json -f callisto_core/wizard_builder/fixtures/wizard_builder_data.json -I
