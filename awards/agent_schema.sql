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
