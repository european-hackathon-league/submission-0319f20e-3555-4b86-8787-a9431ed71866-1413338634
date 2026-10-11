-- Pod A: signals and sentiment over time (notes/signals-and-sentiment.md). Adds to 0009 only:
-- the human editor of a watchlist, the Exa provenance of each monitoring item, sentiment relevance
-- and details, and a recreated v_sentiment_weekly that keeps every 0009 column.

-- Editing a standing search (terms, competitors, domains, cadence) re-authorises it: human only.
ALTER TABLE watchlists ADD COLUMN updated_by TEXT;

-- How the item was found: the template query sent to Exa (never evidence text), the provider result,
-- the cached search-lead snapshot and the publication-date window searched.
ALTER TABLE signal_items ADD COLUMN search_query TEXT;
ALTER TABLE signal_items ADD COLUMN exa_result_id TEXT;
ALTER TABLE signal_items ADD COLUMN candidate_id TEXT;
ALTER TABLE signal_items ADD COLUMN window_start TEXT;
ALTER TABLE signal_items ADD COLUMN window_end TEXT;

-- relevant: the OpenAI method's judgement whether a public item is about the vehicle and topic
-- (NULL when not assessed, e.g. lexicon-v1 or BMW evidence). details: basis, analysed characters,
-- overall polarity, attributes and provider/model labels.
ALTER TABLE sentiment_scores ADD COLUMN relevant INTEGER CHECK(relevant IS NULL OR relevant IN (0, 1));
ALTER TABLE sentiment_scores ADD COLUMN details TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(details));

CREATE INDEX signal_items_watchlist_url ON signal_items(watchlist_id, url_hash);
CREATE INDEX sentiment_scores_method ON sentiment_scores(method_version, subject_type);

CREATE TRIGGER signal_items_provenance_fixed
BEFORE UPDATE OF search_query, exa_result_id, candidate_id, window_start, window_end ON signal_items
WHEN NEW.search_query IS NOT OLD.search_query OR NEW.exa_result_id IS NOT OLD.exa_result_id
  OR NEW.candidate_id IS NOT OLD.candidate_id OR NEW.window_start IS NOT OLD.window_start
  OR NEW.window_end IS NOT OLD.window_end
BEGIN SELECT RAISE(ABORT, 'signal items are reviewed once; their content is fixed'); END;

CREATE TRIGGER watchlists_edit_human
BEFORE UPDATE OF topic, label, query_terms, competitors, domain_group, domains, cadence_days, max_results, rationale
ON watchlists
WHEN NEW.topic IS NOT OLD.topic OR NEW.label IS NOT OLD.label OR NEW.query_terms IS NOT OLD.query_terms
  OR NEW.competitors IS NOT OLD.competitors OR NEW.domain_group IS NOT OLD.domain_group
  OR NEW.domains IS NOT OLD.domains OR NEW.cadence_days IS NOT OLD.cadence_days
  OR NEW.max_results IS NOT OLD.max_results OR NEW.rationale IS NOT OLD.rationale
BEGIN
    INSERT INTO actors (id, kind, display_name, role, origin)
    SELECT NEW.updated_by, kind, NEW.updated_by, CASE kind WHEN 'human' THEN 'pm' ELSE kind END, 'discovered'
    FROM (SELECT CASE WHEN lower(NEW.updated_by) GLOB 'ai:*' THEN 'ai'
                      WHEN lower(NEW.updated_by) GLOB 'system:*' THEN 'system' ELSE 'human' END AS kind)
    WHERE NEW.updated_by IS NOT NULL AND NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.updated_by);
    SELECT RAISE(ABORT, 'inactive actor') WHERE EXISTS (SELECT 1 FROM actors WHERE id = NEW.updated_by AND active = 0);
    SELECT RAISE(ABORT, 'this action requires a human actor')
    WHERE NOT EXISTS (SELECT 1 FROM actors WHERE id = NEW.updated_by AND kind = 'human');
END;

-- Same leading columns as 0009. Changes: weeks are Monday-aligned (week_start), so the week spanning
-- New Year is one point instead of 'YYYY-52' + 'YYYY-00'; `week` stays strftime('%Y-%W') of that Monday;
-- iso_week is the ISO 8601 label; PM-dismissed items and scores judged off-topic are excluded.
DROP VIEW v_sentiment_weekly;
CREATE VIEW v_sentiment_weekly AS
WITH scored AS (
    SELECT si.vehicle, si.market, coalesce(s.topic, si.topic) AS topic, 'public_monitoring' AS source_class,
           s.method_version, s.polarity, s.label, coalesce(si.published_at, si.retrieved_at) AS dated_at,
           CASE WHEN si.published_at IS NULL THEN 1 ELSE 0 END AS undated, s.subject_id
    FROM sentiment_scores s JOIN signal_items si ON s.subject_type = 'signal_item' AND si.id = s.subject_id
    WHERE si.review_status <> 'dismissed' AND coalesce(s.relevant, 1) = 1
    UNION ALL
    SELECT e.vehicle, e.market, s.topic, CASE WHEN src.kind = 'web' THEN 'public_imported' ELSE 'bmw_evidence' END,
           s.method_version, s.polarity, s.label, coalesce(e.observed_at, e.created_at),
           CASE WHEN e.observed_at IS NULL THEN 1 ELSE 0 END, s.subject_id
    FROM sentiment_scores s JOIN evidence e ON s.subject_type = 'evidence' AND e.id = s.subject_id
    JOIN sources src ON src.id = e.source_id
    WHERE coalesce(s.relevant, 1) = 1
), weekly AS (
    SELECT scored.*, date(dated_at, '-6 days', 'weekday 1') AS week_start FROM scored
)
SELECT vehicle, market, topic, strftime('%Y-%W', week_start) AS week, source_class, method_version,
       count(*) AS n, avg(polarity) AS mean_polarity,
       avg(CASE WHEN label = 'negative' THEN 1.0 ELSE 0.0 END) AS negative_share,
       avg(CASE WHEN label = 'positive' THEN 1.0 ELSE 0.0 END) AS positive_share,
       sum(undated) AS undated_n, json_group_array(subject_id) AS subject_ids,
       week_start,
       strftime('%Y', week_start, '+3 days') || '-W'
           || printf('%02d', (CAST(strftime('%j', week_start, '+3 days') AS INTEGER) - 1) / 7 + 1) AS iso_week,
       avg(CASE WHEN label = 'mixed' THEN 1.0 ELSE 0.0 END) AS mixed_share
FROM weekly
GROUP BY vehicle, market, topic, week_start, source_class, method_version;
