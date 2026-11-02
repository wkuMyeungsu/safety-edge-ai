-- 초안. docs/contracts/ 에서 pi 담당과 합의한 뒤 확정한다.
-- 여러 번 실행해도 오류 없이 같은 결과가 되도록 작성한다.

create table if not exists public.safety_logs (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  device_id   text not null,
  has_helmet  boolean not null,
  has_vest    boolean not null,
  confidence  real,
  image_url   text
);

-- 웹(anon)은 읽기만 한다. 쓰기는 uploader의 service key(RLS 우회)로만 한다.
alter table public.safety_logs enable row level security;

drop policy if exists "anon read safety_logs" on public.safety_logs;
create policy "anon read safety_logs"
  on public.safety_logs for select
  to anon
  using (true);

-- 위반 사진 버킷 (공개 읽기)
insert into storage.buckets (id, name, public)
values ('violations', 'violations', true)
on conflict (id) do nothing;

-- 웹 실시간 갱신
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public' and tablename = 'safety_logs'
  ) then
    alter publication supabase_realtime add table public.safety_logs;
  end if;
end $$;
