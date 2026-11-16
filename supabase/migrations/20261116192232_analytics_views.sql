-- Aggregate-only views for the intern role (and auditors).
-- Views run with the owner's rights, so they read the base tables past RLS; they are
-- safe because (a) they only expose aggregates, (b) groups smaller than 5 are suppressed,
-- and (c) each view still requires a verified intern/auditor identity.
-- security_barrier stops a caller's predicates being pushed below the aggregation.

create or replace view analytics.branch_monthly_flows with (security_barrier) as
select b.branch_id, b.name as branch_name, b.city,
       date_trunc('month', t.txn_at)::date                              as month,
       count(*)                                                         as txn_count,
       sum(t.amount) filter (where t.txn_type in ('deposit', 'transfer_in'))     as inflow_total,
       sum(t.amount) filter (where t.txn_type in ('withdrawal', 'transfer_out')) as outflow_total
  from bank.transactions t
  join bank.branches b using (branch_id)
 where (select app.current_app_role()) in ('intern', 'auditor')
 group by b.branch_id, b.name, b.city, date_trunc('month', t.txn_at)
having count(*) >= 5;

create or replace view analytics.branch_customer_counts with (security_barrier) as
select b.branch_id, b.name as branch_name, c.segment, count(*) as customer_count
  from bank.customers c
  join bank.branches b using (branch_id)
 where (select app.current_app_role()) in ('intern', 'auditor')
 group by b.branch_id, b.name, c.segment
having count(*) >= 5;

create or replace view analytics.loan_portfolio_summary with (security_barrier) as
select b.branch_id, b.name as branch_name, l.loan_type, l.status,
       count(*) as loan_count, sum(l.outstanding) as outstanding_total
  from bank.loans l
  join bank.branches b using (branch_id)
 where (select app.current_app_role()) in ('intern', 'auditor')
 group by b.branch_id, b.name, l.loan_type, l.status
having count(*) >= 5;

create or replace view analytics.headcount_by_branch with (security_barrier) as
select e.branch_id, coalesce(b.name, 'Head Office') as branch_name, e.department,
       count(*) as headcount
  from bank.employees e
  left join bank.branches b using (branch_id)
 where (select app.current_app_role()) in ('intern', 'auditor')
   and e.status = 'active'
 group by e.branch_id, b.name, e.department
having count(*) >= 5;

revoke all on all tables in schema analytics from public;
grant select on all tables in schema analytics to bank_intern, bank_auditor;

-- Supabase only: default privileges can grant new objects to the Data API roles.
-- Strip them from everything in the three private schemas, including these views.
do $$
declare r text;
begin
    foreach r in array array['anon', 'authenticated', 'service_role'] loop
        if exists (select 1 from pg_roles where rolname = r) then
            execute format('revoke all on all tables in schema bank, app, analytics from %I', r);
            execute format('revoke all on all functions in schema app from %I', r);
            execute format('alter default privileges in schema bank, app, analytics revoke all on tables from %I', r);
        end if;
    end loop;
end
$$;
