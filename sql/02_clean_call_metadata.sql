CREATE TABLE
    IF NOT EXISTS clean.call_metadata (
        call_id text GENERATED ALWAYS AS (source_app || ':' || source_call_id) STORED,
        source_app text NOT NULL,
        source_call_id text NOT NULL,
        source_file text NOT NULL,
        company_id text NOT NULL,
        start_time timestamptz NOT NULL,
        end_time timestamptz,
        answered_time timestamptz,
        call_duration_secs numeric(10, 3) CHECK (call_duration_secs >= 0),
        hold_duration_secs numeric(10, 3) NOT NULL DEFAULT 0 CHECK (hold_duration_secs >= 0),
        queue_duration_secs numeric(10, 3) CHECK (queue_duration_secs >= 0),
        wrap_duration_secs numeric(10, 3) NOT NULL DEFAULT 0 CHECK (wrap_duration_secs >= 0),
        total_duration_secs numeric(10, 3) NOT NULL DEFAULT 0 CHECK (total_duration_secs >= 0),
        direction text NOT NULL,
        customer_tel text,
        agent_tel text,
        agent text,
        answered boolean NOT NULL,
        recording_url text,
        recording_uri text,
        transcript_uri text,
        added_time timestamptz NOT NULL DEFAULT now (),
        CONSTRAINT call_pk PRIMARY KEY (call_id)
    );

CREATE INDEX IF NOT EXISTS call_metadata_company_start_idx ON clean.call_metadata (company_id, start_time);