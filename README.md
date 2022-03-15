# Hackathon Automatic Refactoring


Refactor Databricks Notebooks into modules.

## Setup

1. Set the following configurations on a cluster.
```
WSFS_ENABLE_WRITE_SUPPORT=true
```
2. Also export the following environment variables either as a cluster config or on the shell.
```
API_URL=[fill in]
DB_TOKEN=[fill in]
```
3. Clone this repo on the cluster.
3. Runs `pip install -r requirements.txt` from the repo directory.

## Running the Server

From this repo directory, make sure that script.sh has execute permission
```
chmod +x scripts/script.sh
```
then, run 
```
./scripts/script.sh
```

## The API docs
Opens `http://localhost:9999/docs` or `http://localhost:9999/redoc` 
