#!/bin/sh
set -eu
python src/manage.py test CafeDolbeau --noinput
node --test src/CafeDolbeau/tests_js/*.test.cjs
