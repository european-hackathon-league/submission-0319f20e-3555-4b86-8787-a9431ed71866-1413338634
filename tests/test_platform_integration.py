"""Cross-pod wiring added at integration: shared reads of other pods' tables agree on one selection rule."""

from contextlib import closing

from database.store import connect, transaction
from server import intake, markets, prioritization
from server.platform import record_run


def seed_weights(rows):
    """rows: (id, market, period, share, period_type, status); simulated sales shares for G60."""
    with record_run(None, "simulated.weights", "system:test", "sales-share-v1", {"simulated": True}) as run:
        with transaction() as connection:
            for row_id, market, period, share, period_type, status in rows:
                connection.execute(
                    "INSERT INTO market_weights (id,vehicle,market,period,units,share,evidence_ids,method_version,run_id,"
                    "created_at,status,metrics) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (row_id, "G60", market, period, share * 100, share, '["sales-1"]', "sales-share-v1", run.id,
                     "2026-01-01", status, f'{{"period_type": "{period_type}"}}'))


def test_weight_readers_skip_projection_periods_and_superseded_rows(db):
    seed_weights([
        ("us-2025", "US", "2025", 0.6, "reported", "current"), ("cn-2025", "CN", "2025", 0.4, "reported", "current"),
        ("us-2030", "US", "2030", 0.3, "projection", "current"), ("cn-2030", "CN", "2030", 0.7, "projection", "current"),
        ("us-2026", "US", "2026", 0.9, "reported", "superseded"), ("cn-2026", "CN", "2026", 0.1, "reported", "superseded"),
    ])
    with closing(connect()) as connection:
        selection, rows = markets._weight_selection(connection, "G60", None)
        assert selection["period"] == "2025" and {row["id"] for row in rows} == {"us-2025", "cn-2025"}
        explicit, rows = markets._weight_selection(connection, "G60", "2030")
        assert explicit["period"] == "2030" and {row["id"] for row in rows} == {"us-2030", "cn-2030"}
        shares, _ = prioritization.market_shares(connection, "G60")
        assert shares == {"US": 0.6, "CN": 0.4}
        share = intake._market_share(connection, "G60", "CN")
        assert share["measured"] and share["share"] == 0.4 and share["period"] == "2025"
