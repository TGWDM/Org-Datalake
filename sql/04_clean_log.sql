-- One row per processed file version. Used to skip files already loaded.
CREATE TABLE
    IF NOT EXISTS clean.load_log (
        load_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        source_file text NOT NULL, -- S3 object key
        etag text NOT NULL, -- identifies the file version
        status text NOT NULL CHECK (status IN ('succeeded', 'failed')),
        rows_read integer,
        rows_loaded integer,
        rows_quarantined integer,
        rows_duplicate integer,
        error_message text,
        started_at timestamptz NOT NULL DEFAULT now (),
        finished_at timestamptz
    );

-- A file version can only succeed once; failed attempts can repeat.
CREATE UNIQUE INDEX IF NOT EXISTS load_log_succeeded_uq ON clean.load_log (source_file, etag)
WHERE
    status = 'succeeded';

-- Lookup by file when listing history.
CREATE INDEX IF NOT EXISTS load_log_file_idx ON clean.load_log (source_file);