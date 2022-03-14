#!/bin/sh

# require DB_TOKEN as env variable
# require DB_URL
mkdir -p /tmp/log
touch /tmp/log/refactoring.log
cd refactoring && uvicorn server:app --reload --port 9999 --host 0.0.0.0 2>&1 | tee /tmp/log/refactoring.log
