ALTER TABLE decisions ADD COLUMN scoring_mode TEXT NOT NULL DEFAULT 'rule_only';
ALTER TABLE decisions ADD COLUMN score_kind TEXT NOT NULL DEFAULT 'experimental_score';
ALTER TABLE decisions ADD COLUMN rule_score INTEGER NOT NULL DEFAULT 0;
ALTER TABLE decisions ADD COLUMN ml_normalized_score INTEGER;
ALTER TABLE decisions ADD COLUMN explanation_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE decisions ADD COLUMN feature_snapshot_id TEXT;
ALTER TABLE decisions ADD COLUMN anchor_status TEXT NOT NULL DEFAULT 'NOT_IMPLEMENTED';
ALTER TABLE decisions ADD COLUMN receipt_status TEXT NOT NULL DEFAULT 'NOT_IMPLEMENTED';
