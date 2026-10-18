-- Chat photos and voice notes: only the sender and the people in that chat.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it. Kept here for the same reason as the other files in this folder: a
-- rule that lives only inside the database is invisible to anyone reading the
-- project.
--
-- WHAT WAS WRONG
--
-- The chat_media and voice_messages buckets are private, and uploads were
-- already limited to your own folder. But the read rules were simply
-- "bucket_id = 'chat_media'" and "bucket_id = 'voice_messages'" for any
-- signed-in user. Private from people who are signed out, open to every
-- account. The Terms promise the opposite: media sent in a conversation can
-- be opened by the people in that conversation and nobody else.
--
-- THE FIX
--
-- A file in either bucket can be read by:
--   1. the person who uploaded it (it sits in their own folder), or
--   2. a member of a conversation where THAT SAME PERSON sent a message
--      pointing at it, as long as that message has not been deleted.
--
-- "Not deleted" is what makes a listen-once voice note stop opening for the
-- recipient once it has been played (consume_listen_once marks the message
-- deleted but leaves the link). Before this, only the app enforced it. A
-- signed link already handed out still works until it expires, up to an hour.
--
-- Rule 2 checks the message's sender against the folder owner on purpose. A
-- message can only be sent as yourself (msg_insert), so nobody can grant
-- themselves someone else's file by posting a link to it in a chat of their
-- own. The one way round that was editing an existing message: a group admin
-- may update any message in the group, and nothing stopped that update from
-- changing who sent it or what file it points at. The trigger below closes
-- that: sender and conversation never change, and anyone who is not the
-- sender may only clear the media (what "delete for everyone" does), never
-- point it somewhere else.
--
-- ALSO: chat photos, videos, albums and video notes now upload here. The app
-- used to put them in the PUBLIC images, videos and media buckets, where the
-- link alone opened them. chat_media allowed 50 MB against the videos bucket's
-- 100 MB, so its limit is raised to match and nothing that could be sent
-- before is refused now. Files already in the public buckets stay where they
-- are (1 photo and 1 video on 2026-10-18); moving them is a separate decision.
--
-- IF FORWARDING IS EVER BUILT: copy the file into the forwarder's own folder.
-- Pointing a forwarded message at the original file will not open for the new
-- chat, because rule 2 requires the message's sender to own the file.
--
-- WHAT IS NOT TOUCHED
--
--   * Uploading, replacing and deleting files: already limited to your own
--     folder by the existing policies, which stay as they are.
--   * Signed links already handed out keep working until they expire (the
--     app asks for one-hour links).
--   * The server's service key bypasses all of this, as it should.
--   * The read receipt, delivery and listen-once functions update messages
--     without changing sender, conversation or media, so the trigger lets
--     them through unchanged.
--
-- Reviewed against pg_policies, storage.buckets and the messages columns on
-- 2026-10-18: 2 files in chat_media, 5 in voice_messages, no group chats yet.
--
-- Applied to production: NOT YET. (Fill the date on apply.)

begin;

-- Who may read one file. SECURITY DEFINER so it can look at messages and
-- participants whatever the caller's own row rules say; it answers only yes or
-- no, about one file, for the person asking.
create or replace function public.tf_can_read_chat_object(p_bucket text, p_name text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
    select auth.uid() is not null and (
        -- 1. Your own upload.
        (storage.foldername(p_name))[1] = auth.uid()::text
        or
        -- 2. Sent by its owner into a conversation you are in, and not deleted.
        exists (
            select 1
            from public.messages m
            where m.sender_id::text = (storage.foldername(p_name))[1]
              and m.conversation_id in (select public.my_conv_ids())
              and coalesce(m.is_deleted, false) = false
              and (
                    strpos(coalesce(m.media_url, ''), '/' || p_bucket || '/' || p_name) > 0
                 or strpos(coalesce(m.media_urls::text, ''), '/' || p_bucket || '/' || p_name) > 0
              )
        )
    );
$$;

revoke all on function public.tf_can_read_chat_object(text, text) from public, anon;
grant execute on function public.tf_can_read_chat_object(text, text) to authenticated;

drop policy if exists "Auth read chat_media" on storage.objects;
drop policy if exists "Auth read voice_messages" on storage.objects;
-- So pasting this twice is harmless.
drop policy if exists "Chat media: sender and conversation members read" on storage.objects;
drop policy if exists "Voice messages: sender and conversation members read" on storage.objects;

create policy "Chat media: sender and conversation members read"
    on storage.objects for select to authenticated
    using (bucket_id = 'chat_media' and public.tf_can_read_chat_object(bucket_id, name));

create policy "Voice messages: sender and conversation members read"
    on storage.objects for select to authenticated
    using (bucket_id = 'voice_messages' and public.tf_can_read_chat_object(bucket_id, name));

-- A message keeps its sender and its conversation for life, and only its sender
-- can change what it points at. The server (no signed-in user) is exempt so it
-- can still correct or clean up rows.
create or replace function public.tf_guard_message_update()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    if auth.uid() is null then
        return new;
    end if;
    if new.sender_id is distinct from old.sender_id
       or new.conversation_id is distinct from old.conversation_id then
        raise exception 'A message cannot change who sent it or which conversation it is in';
    end if;
    if old.sender_id is distinct from auth.uid() then
        if (new.media_url is not null and new.media_url is distinct from old.media_url)
           or (new.media_urls is not null and new.media_urls is distinct from old.media_urls) then
            raise exception 'Only the sender can change what a message points to';
        end if;
    end if;
    return new;
end;
$$;

drop trigger if exists tf_guard_message_update on public.messages;
create trigger tf_guard_message_update
    before update on public.messages
    for each row execute function public.tf_guard_message_update();

-- Room for chat videos: the same 100 MB and video types as the videos bucket.
update storage.buckets
   set file_size_limit = greatest(coalesce(file_size_limit, 0), 104857600),
       allowed_mime_types = (select array_agg(distinct t order by t)
                               from unnest(allowed_mime_types || array['video/x-m4v']) as t)
 where id = 'chat_media';

commit;

-- ---------------------------------------------------------------------------
-- CHECK (read-only; run after applying)
-- ---------------------------------------------------------------------------
-- Two read policies, both calling tf_can_read_chat_object, and the trigger:
--
-- select policyname, cmd, qual from pg_policies
--  where schemaname = 'storage' and tablename = 'objects' and cmd = 'SELECT'
--    and qual ~ '(chat_media|voice_messages)';
-- select tgname from pg_trigger
--  where tgrelid = 'public.messages'::regclass and tgname = 'tf_guard_message_update';
-- select file_size_limit, 'video/x-m4v' = any(allowed_mime_types) as m4v
--   from storage.buckets where id = 'chat_media';

-- ---------------------------------------------------------------------------
-- ROLLBACK (restores the previous rules exactly; run only if needed)
-- ---------------------------------------------------------------------------
-- begin;
-- drop policy if exists "Chat media: sender and conversation members read" on storage.objects;
-- drop policy if exists "Voice messages: sender and conversation members read" on storage.objects;
-- create policy "Auth read chat_media" on storage.objects for select to authenticated
--   using (bucket_id = 'chat_media'::text);
-- create policy "Auth read voice_messages" on storage.objects for select to authenticated
--   using (bucket_id = 'voice_messages'::text);
-- drop trigger if exists tf_guard_message_update on public.messages;
-- drop function if exists public.tf_guard_message_update();
-- drop function if exists public.tf_can_read_chat_object(text, text);
-- update storage.buckets set file_size_limit = 52428800,
--        allowed_mime_types = array_remove(allowed_mime_types, 'video/x-m4v')
--  where id = 'chat_media';
-- commit;
