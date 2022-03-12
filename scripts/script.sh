#!/bin/sh

# require DB_TOKEN as env variable
# require DB_URL
cd refactoring && uvicorn server:app --reload --port 9999