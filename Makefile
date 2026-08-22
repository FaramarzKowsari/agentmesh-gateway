.PHONY: install lint test run

install:
	python -m pip install -e '.[dev]'

lint:
	ruff check .

test:
	pytest

run:
	agentmesh serve --reload
