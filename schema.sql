CREATE TABLE IF NOT EXISTS tests (
 id BIGSERIAL PRIMARY KEY,
 creator_id TEXT NOT NULL,
 title TEXT NOT NULL,
 description TEXT NOT NULL DEFAULT '',
 duration_minutes INTEGER NOT NULL DEFAULT 30,
 max_attempts INTEGER NOT NULL DEFAULT 1,
 share_code TEXT UNIQUE NOT NULL,
 is_published BOOLEAN NOT NULL DEFAULT FALSE,
 shuffle_questions BOOLEAN NOT NULL DEFAULT FALSE,
 show_score BOOLEAN NOT NULL DEFAULT TRUE,
 show_correct_answers BOOLEAN NOT NULL DEFAULT FALSE,
 terminate_on_violation BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS questions (
 id BIGSERIAL PRIMARY KEY,
 test_id BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
 question_text TEXT NOT NULL,
 kind TEXT NOT NULL CHECK (kind IN ('single','multiple')),
 marks NUMERIC(8,2) NOT NULL DEFAULT 1,
 negative_marks NUMERIC(8,2) NOT NULL DEFAULT 0,
 position INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS options (
 id BIGSERIAL PRIMARY KEY,
 question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
 option_text TEXT NOT NULL,
 is_correct BOOLEAN NOT NULL DEFAULT FALSE,
 position INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS attempts (
 id BIGSERIAL PRIMARY KEY,
 test_id BIGINT NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
 student_name TEXT NOT NULL,
 candidate_id TEXT NOT NULL,
 started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 submitted_at TIMESTAMPTZ,
 status TEXT NOT NULL DEFAULT 'in_progress',
 score NUMERIC(10,2),
 max_score NUMERIC(10,2)
);
CREATE INDEX IF NOT EXISTS attempts_candidate_idx ON attempts(test_id,candidate_id);
CREATE TABLE IF NOT EXISTS responses (
 attempt_id BIGINT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
 question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
 option_id BIGINT NOT NULL REFERENCES options(id) ON DELETE CASCADE,
 PRIMARY KEY(attempt_id,question_id,option_id)
);
CREATE TABLE IF NOT EXISTS security_events (
 id BIGSERIAL PRIMARY KEY,
 attempt_id BIGINT NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
 event_type TEXT NOT NULL,
 details JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS platform_events (
 id BIGSERIAL PRIMARY KEY,
 event_type TEXT NOT NULL,
 email TEXT,
 creator_id TEXT,
 test_id BIGINT,
 details JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS platform_events_type_idx ON platform_events(event_type,created_at DESC);
