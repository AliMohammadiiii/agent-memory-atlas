UV ?= uv
PYTHON_VERSION ?= 3.12
OUTPUT ?= /tmp/atlas-demo
PYTHON = $(UV) run --python $(PYTHON_VERSION) --no-project --with-requirements requirements-test.txt python

.PHONY: demo test test-python test-frontend build-frontend

demo:
	$(PYTHON) -m atlas_demo --output "$(OUTPUT)"

test: test-python test-frontend

test-python:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:scripts:server $(PYTHON) -m pytest -p no:cacheprovider scripts server tests -q

test-frontend:
	npm --prefix site test

build-frontend:
	npm --prefix site run build
