ALTER TABLE decisions ADD COLUMN schema_version TEXT NOT NULL DEFAULT '1.1';
ALTER TABLE decisions ADD COLUMN ruleset_sha256 TEXT;
ALTER TABLE decisions ADD COLUMN source_ref_json TEXT;
