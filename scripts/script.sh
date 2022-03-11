#!/bin/sh

# require DB_TOKEN as env variable
# require DB_URL
cd refactoring-server && uvicorn main:app --reload --port 9999