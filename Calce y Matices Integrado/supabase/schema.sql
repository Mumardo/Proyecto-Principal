create table if not exists public.user_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  bust numeric,
  waist numeric,
  hip numeric,
  remember_measurements boolean not null default false,
  remember_photo boolean not null default false,
  photo_path text,
  color_palette jsonb not null default '[]'::jsonb
    check (jsonb_typeof(color_palette) = 'array'),
  updated_at timestamptz not null default now()
);

alter table public.user_profiles
  add column if not exists remember_measurements boolean not null default false,
  add column if not exists remember_photo boolean not null default false,
  add column if not exists photo_path text;

update public.user_profiles
set remember_measurements = true
where bust is not null
   or waist is not null
   or hip is not null
   or color_palette <> '[]'::jsonb;

alter table public.user_profiles enable row level security;

revoke all on public.user_profiles from anon;
grant select, insert, update, delete on public.user_profiles to authenticated;

drop policy if exists "Users can read their own profile"
  on public.user_profiles;
create policy "Users can read their own profile"
  on public.user_profiles for select to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can insert their own profile"
  on public.user_profiles;
create policy "Users can insert their own profile"
  on public.user_profiles for insert to authenticated
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can update their own profile"
  on public.user_profiles;
create policy "Users can update their own profile"
  on public.user_profiles for update to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

drop policy if exists "Users can delete their own profile"
  on public.user_profiles;
create policy "Users can delete their own profile"
  on public.user_profiles for delete to authenticated
  using ((select auth.uid()) = user_id);

insert into storage.buckets (
  id,
  name,
  public,
  file_size_limit,
  allowed_mime_types
)
values (
  'user-profile-photos',
  'user-profile-photos',
  false,
  10485760,
  array['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif']
)
on conflict (id) do update
set name = excluded.name,
    public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Users can read their own profile photos"
  on storage.objects;
create policy "Users can read their own profile photos"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'user-profile-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists "Users can upload their own profile photos"
  on storage.objects;
create policy "Users can upload their own profile photos"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'user-profile-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists "Users can update their own profile photos"
  on storage.objects;
create policy "Users can update their own profile photos"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'user-profile-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  )
  with check (
    bucket_id = 'user-profile-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

drop policy if exists "Users can delete their own profile photos"
  on storage.objects;
create policy "Users can delete their own profile photos"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'user-profile-photos'
    and (storage.foldername(name))[1] = (select auth.uid())::text
  );

notify pgrst, 'reload schema';
