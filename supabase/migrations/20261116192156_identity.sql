-- Identity binding.
--
-- The service verifies the user's Supabase JWT, then sets `request.jwt.claims` in a
-- transaction-local setting. On its own that GUC is forgeable: any SQL that runs in
-- the same transaction could call set_config() and claim to be someone else.
--
-- So the claims carry an HMAC over (sub, backend pid, transaction start time), keyed
-- with a secret only these SECURITY DEFINER functions can read. Generated SQL cannot
-- produce a valid signature for a different user, and a signature is useless in any
-- other transaction. If the check fails, current_sub() is NULL and every RLS policy
-- returns zero rows (fail closed).

create or replace function app.txn_binding()
returns table (backend_pid integer, txn_ts_us bigint)
language sql stable
set search_path = ''
as $$
    select pg_catalog.pg_backend_pid(),
           (extract(epoch from pg_catalog.transaction_timestamp()) * 1000000)::bigint
$$;

create or replace function app.current_sub()
returns uuid
language plpgsql stable security definer
set search_path = ''
as $$
declare
    c        jsonb;
    s        text;
    k        bytea;
    expected text;
begin
    c := nullif(current_setting('request.jwt.claims', true), '')::jsonb;
    if c is null then
        return null;
    end if;
    s := c ->> 'sub';
    select ik.secret into k
      from app.identity_keys ik
     where ik.key_id = c ->> 'app_key' and ik.active;
    if s is null or k is null then
        return null;
    end if;
    select encode(extensions.hmac(
               convert_to(s || ':' || b.backend_pid || ':' || b.txn_ts_us, 'UTF8'), k, 'sha256'), 'hex')
      into expected
      from app.txn_binding() b;
    if expected is distinct from (c ->> 'app_sig') then
        return null;
    end if;
    return s::uuid;
exception when others then
    return null;
end
$$;

create or replace function app.current_app_role()
returns text
language sql stable security definer
set search_path = ''
as $$
    select su.app_role from app.staff_users su
     where su.auth_user_id = app.current_sub() and su.active
$$;

create or replace function app.current_branch()
returns smallint
language sql stable security definer
set search_path = ''
as $$
    select su.branch_id from app.staff_users su
     where su.auth_user_id = app.current_sub() and su.active
$$;

-- Used by the service to choose which Postgres role to SET for this transaction.
create or replace function app.whoami()
returns table (auth_user_id uuid, app_role text, branch_id smallint)
language sql stable security definer
set search_path = ''
as $$
    select su.auth_user_id, su.app_role, su.branch_id from app.staff_users su
     where su.auth_user_id = app.current_sub() and su.active
$$;

-- NOTE: there is deliberately no function that returns the key. Generated SQL can call
-- set_config('role', ...) to switch back to the session (login) role, so anything the
-- login role can read, an attacker's SELECT can read too. The service holds its own copy
-- of the key (env secret); the database copy is reachable only inside current_sub().

revoke all on all functions in schema app from public;
