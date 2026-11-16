-- Row-level security. Every policy checks BOTH:
--   1. the Postgres role it is attached to (TO bank_x), and
--   2. the app role of the HMAC-verified identity (app.current_app_role()).
-- So switching Postgres role inside a query (set_config('role', ...)) gains nothing:
-- a teller identity running as bank_hr matches no HR policy and sees zero rows.
--
-- Helper calls are wrapped in (select ...) so Postgres evaluates them once per query.
-- Tables are not FORCE'd: the owner (migration role) must still read them to build the
-- aggregate views in the analytics schema. The service never connects as the owner.

alter table bank.branches     enable row level security;
alter table bank.customers    enable row level security;
alter table bank.accounts     enable row level security;
alter table bank.transactions enable row level security;
alter table bank.loans        enable row level security;
alter table bank.employees    enable row level security;
alter table bank.salaries     enable row level security;
alter table app.staff_users   enable row level security;  -- no policies: invisible to all but the owner
alter table app.identity_keys enable row level security;
alter table app.dataset_meta  enable row level security;

-- Branch directory: any verified staff identity.
create policy branches_any_staff on bank.branches for select
    to bank_teller, bank_branch_manager, bank_hr, bank_auditor, bank_intern
    using ((select app.current_app_role()) is not null);

-- Customers / accounts / transactions: own branch for tellers and managers, all for auditors.
create policy customers_own_branch on bank.customers for select
    to bank_teller, bank_branch_manager
    using ((select app.current_app_role()) in ('teller', 'branch_manager')
           and branch_id = (select app.current_branch()));
create policy customers_auditor on bank.customers for select
    to bank_auditor
    using ((select app.current_app_role()) = 'auditor');

create policy accounts_own_branch on bank.accounts for select
    to bank_teller, bank_branch_manager
    using ((select app.current_app_role()) in ('teller', 'branch_manager')
           and branch_id = (select app.current_branch()));
create policy accounts_auditor on bank.accounts for select
    to bank_auditor
    using ((select app.current_app_role()) = 'auditor');

create policy transactions_own_branch on bank.transactions for select
    to bank_teller, bank_branch_manager
    using ((select app.current_app_role()) in ('teller', 'branch_manager')
           and branch_id = (select app.current_branch()));
create policy transactions_auditor on bank.transactions for select
    to bank_auditor
    using ((select app.current_app_role()) = 'auditor');

-- Loans: managers (own branch) and auditors. Tellers have no grant at all.
create policy loans_manager on bank.loans for select
    to bank_branch_manager
    using ((select app.current_app_role()) = 'branch_manager'
           and branch_id = (select app.current_branch()));
create policy loans_auditor on bank.loans for select
    to bank_auditor
    using ((select app.current_app_role()) = 'auditor');

-- Employees: manager sees own-branch staff list; HR and auditor see all.
create policy employees_manager on bank.employees for select
    to bank_branch_manager
    using ((select app.current_app_role()) = 'branch_manager'
           and branch_id = (select app.current_branch()));
create policy employees_hr on bank.employees for select
    to bank_hr
    using ((select app.current_app_role()) = 'hr');
create policy employees_auditor on bank.employees for select
    to bank_auditor
    using ((select app.current_app_role()) = 'auditor');

-- Salaries: HR and auditor all; manager only for staff of their own branch.
create policy salaries_manager on bank.salaries for select
    to bank_branch_manager
    using ((select app.current_app_role()) = 'branch_manager'
           and exists (select 1 from bank.employees e
                        where e.employee_id = salaries.employee_id
                          and e.branch_id = (select app.current_branch())));
create policy salaries_hr on bank.salaries for select
    to bank_hr
    using ((select app.current_app_role()) = 'hr');
create policy salaries_auditor on bank.salaries for select
    to bank_auditor
    using ((select app.current_app_role()) = 'auditor');
