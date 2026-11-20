-- PrepAI Supabase security hardening and question provenance
-- Applied to project rwtapmxgqufjtvkulsnw on 2026-11-20.
-- Flask connects server-side as postgres (BYPASSRLS); browser-facing API roles
-- receive read-only catalogue access and no access to accounts or results.

begin;

alter table public.users enable row level security;
alter table public.companies enable row level security;
alter table public.papers enable row level security;
alter table public.sections enable row level security;
alter table public.questions enable row level security;
alter table public.results enable row level security;
alter table public.result_answers enable row level security;
alter table public.interview_result enable row level security;

drop policy if exists "public_read_companies" on public.companies;
drop policy if exists "public_read_papers" on public.papers;
drop policy if exists "public_read_sections" on public.sections;
drop policy if exists "public_read_questions" on public.questions;

revoke all privileges on table
  public.users, public.companies, public.papers, public.sections,
  public.questions, public.results, public.result_answers, public.interview_result
from anon, authenticated;

grant select on table public.companies, public.papers, public.sections, public.questions
to anon, authenticated;

create policy "public_read_companies" on public.companies
for select to anon, authenticated using (true);
create policy "public_read_papers" on public.papers
for select to anon, authenticated using (true);
create policy "public_read_sections" on public.sections
for select to anon, authenticated using (true);
create policy "public_read_questions" on public.questions
for select to anon, authenticated using (true);

alter table public.questions
  add column if not exists source_type text not null default 'generated_practice',
  add column if not exists source_name text not null default 'PrepAI generated practice',
  add column if not exists source_url text,
  add column if not exists verified_at timestamptz;

alter table public.questions
  drop constraint if exists questions_source_type_check;
alter table public.questions
  add constraint questions_source_type_check
  check (source_type in ('generated_practice','official_previous_year','curated_reference'));

commit;
