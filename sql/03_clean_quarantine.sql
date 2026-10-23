-- Rows that failed validation. Nothing is silently dropped.
CREATE TABLE
    IF NOT EXISTS clean.call_quarantine (
        quarantine_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        source_file text NOT NULL, -- S3 object key
        source_row_number integer NOT NULL, -- position in that file
        raw_row jsonb NOT NULL, -- original row, untouched
        reason text NOT NULL, -- consistent code, e.g. negative_duration
        source_app text, -- nullable: may be the thing that failed
        company_id text,
        resolved boolean NOT NULL DEFAULT false,
        quarantined_at timestamptz NOT NULL DEFAULT now (),
        CONSTRAINT call_quarantine_row_uq UNIQUE (source_file, source_row_number)
    );

-- "Which failures are still open, and why?"
CREATE INDEX IF NOT EXISTS call_quarantine_open_reason_idx ON clean.call_quarantine (reason)
WHERE
    NOT resolved;