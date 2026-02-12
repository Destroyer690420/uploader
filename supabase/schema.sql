-- =====================================================
-- Personal Video Uploader Schema
-- Run this in your Supabase SQL Editor
-- =====================================================

-- Enable UUID extension if not already enabled
create extension if not exists "uuid-ossp";

-- =====================================================
-- API Credentials Table
-- Stores OAuth tokens for YouTube and Instagram
-- =====================================================
create table if not exists public.api_credentials (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  platform text not null check (platform in ('youtube', 'instagram')),
  access_token text,
  refresh_token text,
  token_expiry timestamp with time zone,
  account_id text, -- YouTube Client ID or Instagram Business Account ID
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now(),
  
  -- Ensure one entry per platform per user
  unique(user_id, platform)
);

-- Enable RLS
alter table public.api_credentials enable row level security;

-- RLS Policies: Users can only access their own credentials
create policy "Users can view own credentials"
  on public.api_credentials for select
  using (auth.uid() = user_id);

create policy "Users can insert own credentials"
  on public.api_credentials for insert
  with check (auth.uid() = user_id);

create policy "Users can update own credentials"
  on public.api_credentials for update
  using (auth.uid() = user_id);

create policy "Users can delete own credentials"
  on public.api_credentials for delete
  using (auth.uid() = user_id);

-- Index for faster lookups
create index if not exists idx_api_credentials_user_platform 
  on public.api_credentials(user_id, platform);

-- =====================================================
-- Storage Bucket: temp_video_queue
-- =====================================================
-- Note: Run this in Supabase Dashboard > Storage > Create new bucket
-- Or use the following SQL (may need Storage Admin privileges):

insert into storage.buckets (id, name, public)
values ('temp_video_queue', 'temp_video_queue', true)
on conflict (id) do nothing;

-- Storage Policies
-- Allow authenticated users to upload
create policy "Authenticated users can upload videos"
  on storage.objects for insert
  with check (
    bucket_id = 'temp_video_queue' 
    and auth.role() = 'authenticated'
  );

-- Allow authenticated users to delete their uploads
create policy "Authenticated users can delete videos"
  on storage.objects for delete
  using (
    bucket_id = 'temp_video_queue' 
    and auth.role() = 'authenticated'
  );

-- Allow public read access (needed for Instagram API)
create policy "Public can read videos"
  on storage.objects for select
  using (bucket_id = 'temp_video_queue');

-- =====================================================
-- Optional: Upload Logs Table (for debugging)
-- =====================================================
create table if not exists public.upload_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  video_filename text not null,
  caption text,
  youtube_status text,
  youtube_video_id text,
  instagram_status text,
  instagram_media_id text,
  error_message text,
  created_at timestamp with time zone default now()
);

-- Enable RLS
alter table public.upload_logs enable row level security;

create policy "Users can view own logs"
  on public.upload_logs for select
  using (auth.uid() = user_id);

create policy "Service role can insert logs"
  on public.upload_logs for insert
  with check (true);

-- =====================================================
-- Video Queue Table
-- Stores downloaded tweet videos pending upload
-- =====================================================
create table if not exists public.video_queue (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  tweet_url text not null,
  video_filename text not null,
  caption text,
  status text default 'pending' check (status in ('pending', 'uploading', 'completed', 'failed')),
  created_at timestamp with time zone default now()
);

-- Enable RLS
alter table public.video_queue enable row level security;

-- RLS Policies
create policy "Users can view own queue"
  on public.video_queue for select
  using (auth.uid() = user_id);

create policy "Users can insert to own queue"
  on public.video_queue for insert
  with check (auth.uid() = user_id);

create policy "Users can update own queue"
  on public.video_queue for update
  using (auth.uid() = user_id);

create policy "Users can delete from own queue"
  on public.video_queue for delete
  using (auth.uid() = user_id);

-- Service role can manage all queue items (for server.js)
create policy "Service role can manage queue"
  on public.video_queue for all
  using (true)
  with check (true);

-- Index for faster lookups
create index if not exists idx_video_queue_user_status 
  on public.video_queue(user_id, status);
