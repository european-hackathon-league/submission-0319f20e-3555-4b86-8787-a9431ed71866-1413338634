# Local database

The API uses SQLite at `database/local/app.db` and creates the schema on startup. This directory is bind-mounted into the API container, so data survives `docker compose down` and rebuilds. The separate `data/` directory remains reserved for the original BMW input files.

Create a consistent snapshot while the API is running:

```sh
docker compose exec api python -m database.snapshot
```

Snapshots appear in `database/snapshots/`. They contain the SQLite records. Preserve `database/local/originals/` alongside them: those content-addressed original uploads are necessary for source downloads after restoration. They are immutable and remain outside the images and Git. The supplied BMW inputs in `data/` should also be retained separately.

Both the live database and snapshots are local-only and ignored by Git. To restore, stop the stack, preserve the current database and WAL/SHM files, copy a snapshot over `database/local/app.db`, move any old `app.db-wal` and `app.db-shm` files aside, ensure the corresponding originals directory is present, then restart the stack. Do not replace a live database. The snapshot command uses SQLite's backup API, so taking a snapshot while the API runs is safe.
