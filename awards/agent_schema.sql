-- Design 08: the agent's own schema (memory checkpoints + human review queue). Applied by the Entra admin.
-- Award data is NOT here: no role the app holds can write public.awards / public.transactions.
CREATE SCHEMA IF NOT EXISTS agent;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'copilot_agent') THEN
    CREATE ROLE copilot_agent NOLOGIN;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS agent.review_items (
  id             bigserial PRIMARY KEY,
  created_at     timestamptz NOT NULL DEFAULT now(),
  thread_id      text,
  award_key      text NOT NULL,
  piid           text,
  rule_id        text NOT NULL,
  statement      text NOT NULL,
  human_question text NOT NULL,
  evidence       jsonb NOT NULL,
  far_sections   text[] NOT NULL,
  status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'confirmed', 'dismissed')),
  reviewer_oid   text,
  decided_at     timestamptz,
  note           text
);
-- One open item per award + rule: re-running a check doesn't flood the queue.
CREATE UNIQUE INDEX IF NOT EXISTS review_items_one_open ON agent.review_items (award_key, rule_id) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS review_items_status ON agent.review_items (status, created_at);
COMMENT ON TABLE agent.review_items IS 'Competition-check findings awaiting or after human review (design 08). Never a legal verdict.';

GRANT USAGE ON SCHEMA agent TO copilot_agent;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA agent TO copilot_agent;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA agent TO copilot_agent;

-- Design 10: append-only audit log. One row per /ask, /awards/query, /chat request. The question is stored only
-- after PII masking. The app may INSERT and nothing else (privileges below, re-applied by awards.admin setup-agent
-- after its schema-wide grant): it can't rewrite or delete history, or read it back.
CREATE TABLE IF NOT EXISTS agent.audit_log (
  id              bigserial PRIMARY KEY,
  ts              timestamptz NOT NULL DEFAULT now(),
  user_oid        text,
  endpoint        text NOT NULL,
  thread_id       text,
  question_masked text,
  status          text NOT NULL,
  guardrails      jsonb NOT NULL DEFAULT '{}',
  tools           text[] NOT NULL DEFAULT '{}',
  sql             text[] NOT NULL DEFAULT '{}',
  sources         text[] NOT NULL DEFAULT '{}',
  review_ids      bigint[] NOT NULL DEFAULT '{}',
  trace_id        text
);
CREATE INDEX IF NOT EXISTS audit_log_ts ON agent.audit_log (ts);
COMMENT ON TABLE agent.audit_log IS 'Append-only request audit (design 10). App role: INSERT only.';
