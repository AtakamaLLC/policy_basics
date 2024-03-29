SHELL=bash
DELETE_ON_ERROR:

env:
	python -mvirtualenv env

requirements:
	pip install --isolated -r requirements.txt

lint:
	python -m pylint policy_basics
	python -m pylint --rcfile=tests/.pylintrc tests
	python -m pre_commit run insert-license --all-files
	python -m pre_commit run black --all-files

black:
	black policy_basics tests

test:
	python -mpytest --cov policy_basics -v tests

publish:
	rm -rf dist
	python3 setup.py bdist_wheel
	twine upload dist/*

readme:
	python -mdocmd policy_basics > README.md

install-hooks:
	pre-commit install


PHONY: env requirements lint black test publish readme install-hooks
