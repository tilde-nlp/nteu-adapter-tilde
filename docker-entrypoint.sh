#!/bin/sh
exec /sbin/tini -- venv/bin/hypercorn --bind=0.0.0.0:8000 "$@" adapter:app
