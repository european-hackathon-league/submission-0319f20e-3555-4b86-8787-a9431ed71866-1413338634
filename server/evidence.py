"""Source registration and evidence import, preserving originals and exact locations."""

import hashlib
import os
import tempfile
from contextlib import closing, suppress
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError

from database.store import audit, connect, database_path, decode, encode, new_id, now, transaction
from server.models import MAX_IMPORT_BYTES, EvidenceRecord, LocalImport, RecordsImport, Scope, Text, WebImport


class ImportRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def validated(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Invalid input may itself contain NaN or broken Unicode. Avoid
                # serializing it again while reporting the validation failure.
                errors = [{"loc": [part.encode("utf-8", "backslashreplace").decode("utf-8")
                                   if isinstance(part, str) else part for part in error["loc"]],
                           "type": error["type"], "msg": error["msg"].encode("utf-8", "backslashreplace").decode("utf-8")}
                          for error in exc.errors()]
                raise HTTPException(422, errors) from exc

        return validated


router = APIRouter(route_class=ImportRoute)
MAX_FILE_BYTES = MAX_IMPORT_BYTES


def scope_filters(vehicle=None, market=None):
    try:
        scope = Scope(vehicle=vehicle or "G60", market=market or "US")
        if (vehicle is not None and not vehicle.strip()) or (market is not None and not market.strip()):
            raise ValueError("Vehicle and market filters cannot be blank")
    except (ValueError, ValidationError) as exc:
        raise HTTPException(422, "Invalid vehicle or market filter") from exc
    return scope.vehicle if vehicle is not None else None, scope.market if market is not None else None


def preserve_original(name: str, raw: bytes, digest: str):
    """Publish complete bytes atomically; never accept a damaged archive."""
    temporary = None
    try:
        root = (database_path().parent / "originals").resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = root / name
        if not path.resolve().is_relative_to(root):
            raise OSError("Original path escapes the archive")
        if path.exists():
            with path.open("rb") as handle:
                archived = handle.read(MAX_FILE_BYTES + 1)
            if len(archived) > MAX_FILE_BYTES or hashlib.sha256(archived).hexdigest() != digest:
                raise OSError("Archived original does not match its content hash")
            return
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
        temporary.replace(path)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(503, "Original archive is unavailable or damaged") from exc
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


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
    filename = Path((filename or "records.json").replace("\\", "/")).name
    with transaction() as connection:
        existing = connection.execute(
            "SELECT * FROM sources WHERE content_hash = ? AND vehicle = ? AND market = ?",
            (digest, command.vehicle, command.market),
        ).fetchone()
        if existing:
            imported = connection.execute("SELECT * FROM imports WHERE source_id = ?", (existing["id"],)).fetchone()
            if imported is None or not existing["original_path"]:
                raise HTTPException(503, "Imported source is incomplete")
            preserve_original(existing["original_path"], raw, digest)
            return {"source_id": existing["id"], "import_id": imported["id"],
                    "record_count": imported["record_count"], "deduplicated": True, "sha256": digest}
        original_name = digest + Path(filename).suffix.lower()
        source_id, import_id, timestamp = new_id(), new_id(), now()
        dates = {record["observed_at"] for record in records}
        observed_at = dates.pop() if len(dates) == 1 else None
        source = {"id": source_id, "title": command.title, "kind": command.kind,
                  "reference": command.reference, "vehicle": command.vehicle, "market": command.market,
                  "content_hash": digest, "metadata": command.metadata, "original_path": original_name,
                  "created_at": timestamp, "observed_at": observed_at}
        connection.execute(
            "INSERT INTO sources (id,title,kind,reference,vehicle,market,created_at,content_hash,metadata,original_path,observed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (source_id, command.title, command.kind, command.reference, command.vehicle, command.market,
             timestamp, digest, encode(command.metadata), original_name, observed_at),
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
        preserve_original(original_name, raw, digest)
        return {"source_id": source_id, "import_id": import_id, "record_count": count,
                "deduplicated": False, "sha256": digest}


def import_file(filename: str, data: bytes, vehicle="G60", market="US", title=None, kind="document", actor="PM"):
    from server.importers import parse_file

    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "File exceeds the 25 MiB limit")
    filename = Path(filename.replace("\\", "/")).name
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
def file_import(file: UploadFile = File(...), vehicle: Text = Form("G60", max_length=50),
                market: Text = Form("US", max_length=50), title: Text | None = Form(None, max_length=200),
                kind: str = Form("document"), actor: Text = Form("PM", max_length=200)):
    return import_file(file.filename or "input", file.file.read(MAX_FILE_BYTES + 1), vehicle, market, title, kind, actor)


@router.post("/imports/local", status_code=201)
def local_import(command: LocalImport):
    root = Path(os.getenv("DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))).resolve()
    try:
        path = (root / command.path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Invalid local path")
        with path.open("rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(422, "Path must identify a readable file inside DATA_DIR") from exc
    return import_file(path.name, data, command.vehicle, command.market, command.title, command.kind, command.actor)


@router.post("/imports/web", status_code=201)
def web_import(command: WebImport):
    """Import a selected research snapshot with its URL; never execute page content."""
    from server.importers import parse_html

    try:
        parsed = urlparse(command.url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
                or any(char.isspace() or ord(char) < 32 for char in command.url)):
            raise ValueError("Invalid URL")
        parsed.port  # Validate a supplied port even though snapshots do not fetch it.
    except ValueError as exc:
        raise HTTPException(422, "An HTTP(S) source URL without credentials is required") from exc
    content = parse_html(command.content) if "<" in command.content else command.content
    if not content.strip():
        raise HTTPException(422, "The web snapshot contains no readable text")
    blocks = [content[i:i + 50_000] for i in range(0, len(content), 50_000)]
    records = [EvidenceRecord(content=block, location={"url": command.url,
                              "text_offset": i * 50_000 + len(block) - len(block.lstrip())},
                              metadata={"source_type": "web", "snapshot": True, "text_offset_basis": "extracted_text"},
                              observed_at=command.observed_at, vehicle=command.vehicle, market=command.market)
               for i, block in enumerate(blocks) if block.strip()]
    return import_records(RecordsImport(title=command.title, kind="web", reference=command.url,
                                       vehicle=command.vehicle, market=command.market,
                                       records=records, actor=command.actor),
                          original=encode({"url": command.url, "content": command.content,
                                           "observed_at": command.observed_at}).encode(), filename="web.json")


@router.get("/evidence")
def list_evidence(vehicle: str | None = None, market: str | None = None, source_id: str | None = None,
                  q: str | None = Query(None, max_length=5000), limit: int = Query(100, ge=1, le=1000),
                  offset: int = Query(0, ge=0)):
    vehicle, market = scope_filters(vehicle, market)
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
        try:
            root = (database_path().parent / "originals").resolve()
            path = (root / source["original_path"]).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise HTTPException(404, "Original file not available")
            with path.open("rb") as handle:
                archived = handle.read(MAX_FILE_BYTES + 1)
            if len(archived) > MAX_FILE_BYTES or hashlib.sha256(archived).hexdigest() != source["content_hash"]:
                raise OSError("Archived original does not match its content hash")
        except (OSError, RuntimeError) as exc:
            raise HTTPException(503, "Original archive is unavailable or damaged") from exc
        audit(connection, "source", source_id, "source.downloaded", "PM", "Original source accessed")
        imported = connection.execute("SELECT filename FROM imports WHERE source_id=?", (source_id,)).fetchone()
        return FileResponse(path, filename=imported["filename"] if imported else Path(source["reference"]).name)
