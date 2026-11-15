-- Design 06. Applied by the loader as the Entra admin (Aditya). Idempotent.
-- Tables are shaped for Text-to-SQL (feature 07): few tables, plain names, every column commented.

CREATE TABLE IF NOT EXISTS awards (
  fiscal_year                 int     NOT NULL,
  award_key                   text    NOT NULL,
  piid                        text,
  parent_idv_piid             text,
  award_type                  text,
  recipient_name              text,
  recipient_uei               text,
  naics_code                  text,
  naics_description           text,
  psc_code                    text,
  psc_description             text,
  description                 text,
  awarding_office             text,
  pop_state                   text,
  first_action_date           date,
  last_action_date            date,
  action_count                int,
  total_obligated             numeric(18,2),
  current_total_value         numeric(18,2),
  potential_total_value       numeric(18,2),
  extent_competed_code        text,
  extent_competed             text,
  other_than_full_open_code   text,
  other_than_full_open        text,
  far_authority               text,
  solicitation_procedures     text,
  number_of_offers_received   int,
  type_of_set_aside           text,
  fair_opportunity_limited_sources text,
  type_of_contract_pricing    text,
  commercial_item_procedures  text,
  competition_source          text,
  PRIMARY KEY (fiscal_year, award_key)
);

CREATE TABLE IF NOT EXISTS transactions (
  transaction_key             text PRIMARY KEY,
  fiscal_year                 int  NOT NULL,
  award_key                   text NOT NULL,
  modification_number         text,
  action_date                 date,
  action_type                 text,
  federal_action_obligation   numeric(18,2),
  description                 text
);

CREATE TABLE IF NOT EXISTS load_runs (
  id            bigserial PRIMARY KEY,
  fiscal_year   int,
  source        text,
  csv_rows      int,
  transactions  int,
  awards        int,
  started_at    timestamptz,
  finished_at   timestamptz
);

CREATE INDEX IF NOT EXISTS awards_far_authority ON awards (far_authority);
CREATE INDEX IF NOT EXISTS awards_extent_competed ON awards (extent_competed_code);
CREATE INDEX IF NOT EXISTS awards_naics ON awards (naics_code);
CREATE INDEX IF NOT EXISTS awards_recipient ON awards (recipient_name);
CREATE INDEX IF NOT EXISTS tx_award ON transactions (award_key);
CREATE INDEX IF NOT EXISTS tx_action_date ON transactions (action_date);

COMMENT ON TABLE awards IS 'Air Force contract awards (USAspending, contract types A-D). One row per award per fiscal year in which it had at least one action. Competition fields come from the base action (modification 0) when loaded, else the earliest loaded action.';
COMMENT ON COLUMN awards.fiscal_year IS 'Federal fiscal year of the actions summarized (FY2025 = 2024-10-01..2025-09-30)';
COMMENT ON COLUMN awards.award_key IS 'USAspending contract_award_unique_key; joins to transactions.award_key';
COMMENT ON COLUMN awards.piid IS 'Procurement Instrument Identifier (contract or order number)';
COMMENT ON COLUMN awards.parent_idv_piid IS 'PIID of the parent IDV (e.g. IDIQ) for delivery/task orders; NULL for standalone contracts';
COMMENT ON COLUMN awards.award_type IS 'DEFINITIVE CONTRACT, PURCHASE ORDER, DELIVERY ORDER, or BPA CALL';
COMMENT ON COLUMN awards.recipient_name IS 'Contractor (vendor) legal name, upper case';
COMMENT ON COLUMN awards.recipient_uei IS 'Contractor Unique Entity Identifier (SAM.gov)';
COMMENT ON COLUMN awards.naics_code IS 'North American Industry Classification System code (6 digits, text)';
COMMENT ON COLUMN awards.psc_code IS 'Product or Service Code';
COMMENT ON COLUMN awards.description IS 'Description of the base award';
COMMENT ON COLUMN awards.pop_state IS 'Place of performance state code (2 letters)';
COMMENT ON COLUMN awards.action_count IS 'Number of contract actions (base + modifications) in this fiscal year';
COMMENT ON COLUMN awards.total_obligated IS 'Sum of federal_action_obligation over this fiscal year''s actions, USD (can be negative for de-obligations)';
COMMENT ON COLUMN awards.current_total_value IS 'Current total value of the award incl. exercised options, USD, as of the latest loaded action';
COMMENT ON COLUMN awards.potential_total_value IS 'Potential total value incl. all options, USD, as of the latest loaded action';
COMMENT ON COLUMN awards.extent_competed_code IS 'FPDS code: A=full and open, B=not available for competition, C=not competed, D=full and open after exclusion of sources, E=follow-on to competed action, F=competed under SAP, G=not competed under SAP, CDO=competitive delivery order, NDO=non-competitive delivery order';
COMMENT ON COLUMN awards.extent_competed IS 'Readable label for extent_competed_code';
COMMENT ON COLUMN awards.other_than_full_open IS 'Reason not competed, with the FAR authority in the label, e.g. ONLY ONE SOURCE-OTHER (FAR 6.302-1 OTHER)';
COMMENT ON COLUMN awards.far_authority IS 'FAR section parsed from other_than_full_open, e.g. 6.302-1, 6.302-5(a)(2)(i); NULL when competed or no FAR section cited';
COMMENT ON COLUMN awards.number_of_offers_received IS 'Number of offers received; 1 on a competed award is a single-bid signal';
COMMENT ON COLUMN awards.type_of_set_aside IS 'Small business set-aside type, e.g. SMALL BUSINESS SET ASIDE - TOTAL, 8(A) SOLE SOURCE, NO SET ASIDE USED.';
COMMENT ON COLUMN awards.fair_opportunity_limited_sources IS 'For orders under multiple-award IDVs: FAIR OPPORTUNITY GIVEN or the exception used';
COMMENT ON COLUMN awards.type_of_contract_pricing IS 'e.g. FIRM FIXED PRICE, COST PLUS FIXED FEE, TIME AND MATERIALS';
COMMENT ON COLUMN awards.competition_source IS 'base_action if competition fields come from modification 0, else earliest_loaded_action';
COMMENT ON TABLE transactions IS 'Individual contract actions (base award and each modification) for the awards table';
COMMENT ON COLUMN transactions.federal_action_obligation IS 'Dollars obligated (or de-obligated, negative) by this action';
COMMENT ON COLUMN transactions.action_type IS 'Modification type, e.g. FUNDING ONLY ACTION, EXERCISE AN OPTION; empty for the base award';

-- Read-only group role for the app (and Text-to-SQL in 07). NOLOGIN: principals are granted membership.
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'copilot_reader') THEN
    CREATE ROLE copilot_reader NOLOGIN;
  END IF;
END $$;
GRANT CONNECT ON DATABASE copilot TO copilot_reader;
GRANT USAGE ON SCHEMA public TO copilot_reader;
GRANT SELECT ON awards, transactions TO copilot_reader;   -- not load_runs: ops data stays private
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
