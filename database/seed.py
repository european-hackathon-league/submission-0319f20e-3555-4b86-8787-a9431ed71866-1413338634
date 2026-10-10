"""Idempotent reference data: actors, vehicles and markets (notes/database-contract.md)."""

import os
import re
import sqlite3

ACTORS = [
    # (id, kind, display_name, role)
    ("PM", "human", "Product manager (legacy default)", "pm"),
    ("human:troy", "human", "Troy", "lead_pm"),
    ("human:jakob", "human", "Jakob", "pm"),
    ("ai:reference:v1", "ai", "Deterministic reference workflow", "ai"),
    ("system:importer", "system", "Evidence importer", "system"),
    ("system:migration", "system", "Database migrations", "system"),
    ("system:scoring", "system", "Scoring rubric", "system"),
    ("system:cli", "system", "Database CLI", "system"),
]

VEHICLES = [
    # (code, series, body)
    ("G60", "BMW 5 Series", "Sedan"),
    ("G68", "BMW 5 Series", "Sedan, long wheelbase (China)"),
    ("G70", "BMW 7 Series", "Sedan"),
    ("F70", "BMW 1 Series", "Hatchback"),
]

MARKETS = [
    # (code, name, parent_code); parents first.
    ("US", "United States", None),
    ("CN", "China", None),
    ("EU", "Europe (BMW sales region)", None),
    ("DE", "Germany", "EU"),
    ("GB", "United Kingdom", "EU"),
    ("ROW", "Rest of world", None),
]

_SLUG = re.compile(r"[a-z0-9][a-z0-9.-]*")


def ensure_actor(connection: sqlite3.Connection, actor_id: str, kind: str, display_name: str, role: str) -> None:
    """Register an actor if it is missing. Existing actors keep their role and active flag."""
    connection.execute(
        "INSERT INTO actors (id, kind, display_name, role) SELECT ?, ?, ?, ? "
        "WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = ?)",
        (actor_id, kind, display_name, role, actor_id),
    )


def ai_actor_id(provider: str, model: str) -> str:
    """Actor id for an AI provider identity, e.g. ai:openai:gpt-5."""
    slug = re.sub(r"[^a-z0-9.-]+", "-", model.lower()).strip("-")
    if not _SLUG.fullmatch(provider) or not slug:
        raise ValueError(f"Invalid AI actor: {provider}:{model}")
    return f"ai:{provider}:{slug}"


def seed(connection: sqlite3.Connection) -> None:
    for actor in ACTORS:
        ensure_actor(connection, *actor)
    model = os.getenv("OPENAI_MODEL", "").strip()
    if model:
        actor_id = ai_actor_id("openai", model)
        ensure_actor(connection, actor_id, "ai", f"OpenAI {model}", "ai")
    for code, series, body in VEHICLES:
        connection.execute(
            "INSERT INTO vehicles (code, series, body, status) VALUES (?, ?, ?, 'seeded') "
            "ON CONFLICT(code) DO UPDATE SET series = excluded.series, body = excluded.body, "
            "status = CASE WHEN vehicles.status = 'discovered' THEN 'seeded' ELSE vehicles.status END",
            (code, series, body),
        )
    for code, name, parent in MARKETS:
        connection.execute(
            "INSERT INTO markets (code, name, parent_code, status) VALUES (?, ?, ?, 'seeded') "
            "ON CONFLICT(code) DO UPDATE SET name = excluded.name, parent_code = excluded.parent_code, "
            "status = CASE WHEN markets.status = 'discovered' THEN 'seeded' ELSE markets.status END",
            (code, name, parent),
        )
