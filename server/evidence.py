"""Source registration and evidence import, preserving originals and exact locations."""

import hashlib
import os
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from database.store import audit, connect, database_path, decode, encode, new_id, now, transaction
from server.models import EvidenceRecord, LocalImport, RecordsImport, Scope, WebImport

router = APIRouter()
MAX_FILE_BYTES = 25 * 1024 * 1024


def evidence_rows(connection, vehicle=None, market=None, source_ids=None):
    clauses, params = [], []
    for name, value in (("vehicle", vehicle), ("market", market)):
        if value is not None:
            clauses.append(f"{name} = ?")
            params.append(value)
    if source_ids is not None:
        if not source_ids:
            return []
        clauses.append("source_id IN (" + ",".join("?" for _ in source_ids) + ")")
        params.extend(source_ids)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return [decode(row, ("location", "metadata")) for row in connection.execute(
        "SELECT * FROM evidence" + where + " ORDER BY id", params)]


def import_records(command: RecordsImport, original: bytes | None = None, filename: str | None = None) -> dict:
    records = [record.model_dump() for record in command.records]
    if any((record["vehicle"], record["market"]) != (command.vehicle, command.market) for record in records):
        raise HTTPException(422, "Every record must match the import vehicle and market")
    raw = original if original is not None else encode({"records": records, "reference": command.reference}).encode()
    digest = hashlib.sha256(raw).hexdigest()
    filename = Path(filename or "records.json").name
    with transaction() as connection:
        existing = connection.execute(
            "SELECT * FROM sources WHERE content_hash = ? AND vehicle = ? AND market = ?",
            (digest, command.vehicle, command.market),
        ).fetchone()
        if existing:
            imported = connection.execute("SELECT * FROM imports WHERE source_id = ?", (existing["id"],)).fetchone()
            return {"source_id": existing["id"], "import_id": imported["id"],
                    "record_count": imported["record_count"], "deduplicated": True, "sha256": digest}
        original_dir = database_path().parent / "originals"
        original_dir.mkdir(parents=True, exist_ok=True)
        original_name = digest + Path(filename).suffix.lower()
        original_path = original_dir / original_name
        # Content-addressed names never overwrite a different original.
        if not original_path.exists():
            with original_path.open("xb") as handle:
                handle.write(raw)
        source_id, import_id, timestamp = new_id(), new_id(), now()
        source = {"id": source_id, "title": command.title, "kind": command.kind,
                  "reference": command.reference, "vehicle": command.vehicle, "market": command.market,
                  "content_hash": digest, "metadata": command.metadata, "original_path": original_name,
                  "created_at": timestamp}
        connection.execute(
            "INSERT INTO sources (id,title,kind,reference,vehicle,market,created_at,content_hash,metadata,original_path) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (source_id, command.title, command.kind, command.reference, command.vehicle, command.market,
             timestamp, digest, encode(command.metadata), original_name),
        )
        count = 0
        for record in records:
            record_hash = hashlib.sha256(encode(record).encode()).hexdigest()
            result = connection.execute(
                "INSERT OR IGNORE INTO evidence "
                "(id,source_id,vehicle,market,content,location,metadata,observed_at,content_hash,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (new_id(), source_id, command.vehicle, command.market, record["content"],
                 encode(record["location"]), encode(record["metadata"]), record["observed_at"], record_hash, timestamp),
            )
            count += result.rowcount
        connection.execute("INSERT INTO imports VALUES (?,?,?,?,?)", (import_id, source_id, filename, count, timestamp))
        audit(connection, "source", source_id, "source.imported", command.actor,
              "Imported original and located evidence", after=source,
              metadata={"import_id": import_id, "record_count": count, "sha256": digest})
        return {"source_id": source_id, "import_id": import_id, "record_count": count,
                "deduplicated": False, "sha256": digest}


def import_file(filename: str, data: bytes, vehicle="G60", market="US", title=None, kind="document", actor="PM"):
    from server.importers import parse_file

    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "File exceeds the 25 MiB limit")
    try:
        scope = Scope(vehicle=vehicle, market=market)
        records = parse_file(filename, data, scope.vehicle, scope.market)
        if not records:
            raise ValueError("No evidence found for this vehicle and market")
        command = RecordsImport(title=title or Path(filename).name, kind=kind, reference=Path(filename).name,
                                vehicle=scope.vehicle, market=scope.market, records=records, actor=actor,
                                metadata={"filename": Path(filename).name, "dates": "Only dates present in the source are used"})
    except ValidationError as exc:
        raise HTTPException(422, "Invalid import scope or parsed record: " + str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return import_records(command, data, filename)


@router.post("/imports/records", status_code=201)
def records_import(command: RecordsImport):
    return import_records(command)


@router.post("/imports/files", status_code=201)
def file_import(file: UploadFile = File(...), vehicle: str = Form("G60"), market: str = Form("US"),
                title: str | None = Form(None), kind: str = Form("document"), actor: str = Form("PM")):
    return import_file(file.filename or "input", file.file.read(MAX_FILE_BYTES + 1), vehicle, market, title, kind, actor)


@router.post("/imports/local", status_code=201)
def local_import(command: LocalImport):
    root = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))).resolve()
    path = (root / command.path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(422, "Path must identify an existing file inside DATA_DIR")
    with path.open("rb") as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    return import_file(path.name, data, command.vehicle, command.market, command.title, command.kind, command.actor)


@router.post("/imports/web", status_code=201)
def web_import(command: WebImport):
    """Import a selected research snapshot with its URL; never execute page content."""
    from server.importers import parse_html

    parsed = urlparse(command.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(422, "A public HTTP(S) source URL without credentials is required")
    content = parse_html(command.content) if "<" in command.content else command.content
    if not content.strip():
        raise HTTPException(422, "The web snapshot contains no readable text")
    blocks = [content[i:i + 50_000] for i in range(0, len(content), 50_000)]
    records = [EvidenceRecord(content=block, location={"url": command.url, "text_offset": i * 50_000},
                              metadata={"source_type": "web", "snapshot": True}, observed_at=command.observed_at,
                              vehicle=command.vehicle, market=command.market) for i, block in enumerate(blocks)]
    return import_records(RecordsImport(title=command.title, kind="web", reference=command.url,
                                       vehicle=command.vehicle, market=command.market,
                                       records=records, actor=command.actor),
                          original=encode({"url": command.url, "content": command.content}).encode(), filename="web.json")


@router.get("/evidence")
def list_evidence(vehicle: str | None = None, market: str | None = None, source_id: str | None = None,
                  q: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    clauses, params = [], []
    for name, value in (("vehicle", vehicle), ("market", market), ("source_id", source_id)):
        if value is not None:
            clauses.append(f"{name} = ?")
            params.append(value)
    if q:
        clauses.append("instr(lower(content), lower(?)) > 0")
        params.append(q)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with closing(connect()) as connection:
        total = connection.execute("SELECT count(*) FROM evidence" + where, params).fetchone()[0]
        rows = connection.execute("SELECT * FROM evidence" + where + " ORDER BY created_at,id LIMIT ? OFFSET ?",
                                  [*params, limit, offset]).fetchall()
    return {"items": [decode(row, ("location", "metadata")) for row in rows], "total": total,
            "limit": limit, "offset": offset}


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str):
    with transaction() as connection:
        result = decode(connection.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone(),
                        ("location", "metadata"))
        if result is None:
            raise HTTPException(404, "Evidence not found")
        audit(connection, "evidence", evidence_id, "evidence.viewed", "PM", "Evidence detail accessed")
        return result


@router.get("/sources/{source_id}/original")
def get_original(source_id: str):
    with transaction() as connection:
        source = connection.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if source is None or not source["original_path"]:
            raise HTTPException(404, "Original file not available")
        root = (database_path().parent / "originals").resolve()
        path = (root / source["original_path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(404, "Original file not available")
        audit(connection, "source", source_id, "source.downloaded", "PM", "Original source accessed")
        return FileResponse(path, filename=Path(source["reference"]).name)
