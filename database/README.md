# Local database

The API uses SQLite at `database/local/app.db` and creates the schema on startup. This directory is bind-mounted into the API container, so data survives `docker compose down` and rebuilds. The separate `data/` directory remains reserved for the original BMW input files.

Create a consistent snapshot while the API is running:

```sh
docker compose exec api python -m database.snapshot
```

Snapshots appear in `database/snapshots/`. Both the live database and snapshots are local-only and ignored by Git. To restore, stop the stack, copy a snapshot over `database/local/app.db`, remove any old `app.db-wal` and `app.db-shm` files, then restart the stack. Keep a copy of the current database before restoring.
