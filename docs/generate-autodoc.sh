#!/bin/bash


# sphinx-quickstart needs to be invoked once
# when the documentation is first created:
# $ sphinx-quickstart --project libgs --makefile --batchfile --ext-autodoc --ext-doctest --ext-intersphinx --ext-todo --ext-coverage --ext-viewcode --sep --dot _ -a UNSW --quiet ./
# This file can then be used to update the autodoc

# NOTE libgs and sphinx need to be installed first
# $ virtualenv _venv 
# $ source _venv/bin/activate 
# $ pip install -r requirements-doc


sphinx-apidoc -e -o ./source/autodoc ../src/libgs

