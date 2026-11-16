-- Postgres roles and grants.
--
-- sql_agent_login : the ONLY role the service logs in as. NOINHERIT and no grants of its own,
--                   so it can do nothing until it SETs one of the business roles below.
-- bank_*          : one NOLOGIN role per business role. Grants here are the per-role
--                   table/column allowlist; RLS (next migration) filters rows.
--
-- The login password is set outside migrations:
--   alter role sql_agent_login password '<from secret manager>';

do $$
declare r text;
begin
    foreach r in array array['bank_teller', 'bank_branch_manager', 'bank_hr', 'bank_auditor', 'bank_intern'] loop
        if not exists (select 1 from pg_roles where rolname = r) then
            execute format('create role %I nologin noinherit', r);
        end if;
    end loop;
    if not exists (select 1 from pg_roles where rolname = 'sql_agent_login') then
        create role sql_agent_login login noinherit;
    end if;
end
$$;

grant bank_teller, bank_branch_manager, bank_hr, bank_auditor, bank_intern to sql_agent_login;

alter role sql_agent_login set default_transaction_read_only = on;
alter role sql_agent_login set statement_timeout = '5s';
alter role sql_agent_login set idle_in_transaction_session_timeout = '15s';
alter role sql_agent_login set search_path = '';

-- Nobody gets anything by default. Covers Supabase's anon/authenticated via PUBLIC.
revoke all on schema bank, app, analytics from public;
revoke all on all tables in schema bank, app, analytics from public;

do $$
declare r text;
begin
    -- Supabase only: make sure the Data API roles can never read these schemas.
    foreach r in array array['anon', 'authenticated', 'service_role'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on schema bank, app, analytics from %I', r);
            execute format('revoke all on all tables in schema bank, app, analytics from %I', r);
        end if;
    end loop;
end
$$;

-- Identity helpers.
grant usage on schema app to sql_agent_login, bank_teller, bank_branch_manager, bank_hr, bank_auditor, bank_intern;
grant execute on function app.txn_binding(), app.whoami() to sql_agent_login;
grant execute on function app.current_sub(), app.current_app_role(), app.current_branch()
    to bank_teller, bank_branch_manager, bank_hr, bank_auditor, bank_intern;

grant usage on schema bank to bank_teller, bank_branch_manager, bank_hr, bank_auditor, bank_intern;

-- Everyone may read the branch directory.
grant select on bank.branches to bank_teller, bank_branch_manager, bank_hr, bank_auditor, bank_intern;

-- Teller: own-branch customers, accounts, transactions.
grant select on bank.customers, bank.accounts, bank.transactions to bank_teller;

-- Branch manager: teller scope + loans, staff list, own-branch salaries.
grant select on bank.customers, bank.accounts, bank.transactions, bank.loans, bank.employees, bank.salaries
    to bank_branch_manager;

-- HR: employees and salaries, all branches. No customer data.
grant select on bank.employees, bank.salaries to bank_hr;

-- Auditor: everything read-only, but only the MASKED form of PII columns.
grant select (customer_id, branch_id, full_name, date_of_birth, email, city, segment, kyc_status,
              created_at, national_id_masked, phone_masked)
    on bank.customers to bank_auditor;
grant select (account_id, customer_id, branch_id, account_type, status, balance, currency, opened_on,
              closed_on, last_activity_at, account_number_masked)
    on bank.accounts to bank_auditor;
grant select on bank.transactions, bank.loans, bank.salaries to bank_auditor;
grant select (employee_id, branch_id, full_name, job_title, department, email, hired_on, status, phone_masked)
    on bank.employees to bank_auditor;

-- Intern: no base tables beyond the branch directory; aggregate views only (see analytics migration).
grant usage on schema analytics to bank_intern, bank_auditor;
