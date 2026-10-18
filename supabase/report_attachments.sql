-- Screenshots attached to a report: the person reporting and our admins only.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it.
--
-- WHAT WAS WRONG
--
-- A screenshot attached to a report went into the public images bucket, the
-- same one that serves post photos, so its link alone opened it for anyone. A
-- screenshot attached to a report is often of something private: a chat, a
-- threat, someone's details.
--
-- THE FIX
--
-- A private bucket, report_attachments. You can upload only into your own
-- folder; a file opens for the person who uploaded it and for admins
-- (is_admin(), which a user cannot grant themselves: users_guard_privileges
-- forces it false on any row a user creates or edits). The app now uploads
-- here and the admin screen opens screenshots through short-lived signed
-- links.
--
-- Deleting an account deletes its folder here too (tf_delete_account collects
-- files by owner folder). The report itself is kept without the reporter's
-- name; its screenshots go with the account.
--
-- No report screenshots existed on 2026-10-18, so there is nothing to move.
--
-- Applied to production: 2026-10-18, pasted into the Supabase SQL editor by the
-- owner (paste_in_order_2026-10-18.sql) and checked the same day against
-- pg_policies, pg_proc and storage.buckets.

begin;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('report_attachments', 'report_attachments', false, 10485760,
        array['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/heic', 'image/heif'])
on conflict (id) do update
   set public = false,
       file_size_limit = excluded.file_size_limit,
       allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Report screenshots: upload to own folder" on storage.objects;
create policy "Report screenshots: upload to own folder"
    on storage.objects for insert to authenticated
    with check (bucket_id = 'report_attachments'
                and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "Report screenshots: uploader and admins read" on storage.objects;
create policy "Report screenshots: uploader and admins read"
    on storage.objects for select to authenticated
    using (bucket_id = 'report_attachments'
           and ((storage.foldername(name))[1] = auth.uid()::text or public.is_admin()));

drop policy if exists "Report screenshots: uploader deletes own" on storage.objects;
create policy "Report screenshots: uploader deletes own"
    on storage.objects for delete to authenticated
    using (bucket_id = 'report_attachments'
           and (storage.foldername(name))[1] = auth.uid()::text);

commit;

-- ---------------------------------------------------------------------------
-- CHECK (read-only)
-- ---------------------------------------------------------------------------
-- select id, public, file_size_limit from storage.buckets where id = 'report_attachments';
-- select policyname, cmd from pg_policies
--  where schemaname = 'storage' and tablename = 'objects' and policyname like 'Report screenshots:%';

-- ---------------------------------------------------------------------------
-- ROLLBACK (the app would then fail to attach screenshots, and send reports
-- without them, as it already does when an upload fails)
-- ---------------------------------------------------------------------------
-- begin;
-- drop policy if exists "Report screenshots: upload to own folder" on storage.objects;
-- drop policy if exists "Report screenshots: uploader and admins read" on storage.objects;
-- drop policy if exists "Report screenshots: uploader deletes own" on storage.objects;
-- delete from storage.buckets where id = 'report_attachments';  -- only if it is empty
-- commit;
