-- Everything from 2026-10-18 to paste into the Supabase SQL Editor, in order.
--
-- Five independent changes, each in its own transaction and each safe to run
-- twice. Paste this whole file and press Run. If one part stops with an error,
-- the parts before it are already in; fix or report the error and run the file
-- again. Each part's own file in this folder explains it in full and ends with
-- a check and a rollback.
--
--   1. chat_media_access.sql     chat photos and voice notes: only the chat
--   2. account_deletion.sql      "delete my account" deletes everything
--   3. report_attachments.sql    report screenshots: reporter and admins only
--   4. nearby_off.sql            nobody can read anyone's location
--   5. marketplace_listings.sql  the listing post type
--
-- The app changes that rely on these are on the branch
-- claude/payments-startup-google-hosting-nou3cb. Paste this first, then deploy.

-- ═══════════════════════════════════════════════════════════════════════════
-- chat_media_access.sql
-- ═══════════════════════════════════════════════════════════════════════════
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

-- ═══════════════════════════════════════════════════════════════════════════
-- account_deletion.sql
-- ═══════════════════════════════════════════════════════════════════════════
-- Deleting an account deletes what the Terms say it deletes.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it. /api/account/delete/ calls it with the service key.
--
-- WHAT WAS WRONG
--
-- "Delete my account" ran in the browser. It deleted the profile row (posts,
-- comments, likes, follows and stories went with it) and the messages the person
-- sent, then signed out. Left behind: the sign-in record with the email address
-- and password hash, every uploaded file (profile pictures, post photos and
-- videos, stories, chat files, voice notes), and rows in tables the browser
-- never touched. The Terms say "the data goes from our systems rather than being
-- hidden and kept". It did not.
--
-- THE FIX
--
-- tf_delete_account(user) does the database part in one transaction, so it
-- either all happens or none of it does. It:
--   * refuses an account with payment records (wallet transactions,
--     withdrawals, coin history, revenue, a balance or coins). The law makes us
--     keep those, and deleting the sign-in record would break them. Those are
--     closed by hand, on request.
--   * returns the account's files, so the server can remove them through the
--     storage API (deleting storage rows here would orphan the bytes).
--   * unhooks what other people keep: a chat the account started stays for the
--     others in it, a reply to the account's comment stays, a quote stays, a
--     report filed against the account stays for moderation.
--   * deletes everything else that belongs to the account, including rows tied
--     only to the sign-in record, so removing that record afterwards cannot be
--     blocked or leave anything behind.
--
-- The server then deletes the files (Supabase storage and R2) and the sign-in
-- record itself through the auth admin API.
--
-- Reviewed against every foreign key in the public schema on 2026-10-18 and
-- tested on a local PostgreSQL 16 copy of that structure.
--
-- Applied to production: NOT YET. (Fill the date on apply.)

begin;

create or replace function public.tf_delete_account(p_user uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_files jsonb;
begin
    -- Only the server may run this: a signed-in caller carries a user id.
    if auth.uid() is not null then
        raise exception 'not allowed';
    end if;
    if p_user is null or not exists (select 1 from public.users where id = p_user) then
        return jsonb_build_object('ok', false, 'reason', 'not_found');
    end if;
    if p_user = 'edd1e000-0000-4000-8000-000000000001'::uuid then
        return jsonb_build_object('ok', false, 'reason', 'system_account');
    end if;
    if exists (select 1 from public.wallet_transactions where user_id = p_user)
       or exists (select 1 from public.withdrawals where user_id = p_user)
       or exists (select 1 from public.coin_transactions where user_id = p_user)
       or exists (select 1 from public.platform_revenue where from_user = p_user or to_user = p_user)
       or exists (select 1 from public.wallets where user_id = p_user and coalesce(balance, 0) <> 0)
       or exists (select 1 from public.users where id = p_user and coalesce(coins, 0) <> 0) then
        return jsonb_build_object('ok', false, 'reason', 'payment_records');
    end if;

    select coalesce(jsonb_agg(jsonb_build_object('bucket', bucket_id, 'name', name)), '[]'::jsonb)
      into v_files
      from storage.objects
     where (storage.foldername(name))[1] = p_user::text or owner = p_user;

    -- What other people keep, unhooked from this account.
    update public.conversations set created_by = null where created_by = p_user;
    update public.users set parent_id = null where parent_id = p_user;
    update public.users set gold_badge_granted_by = null where gold_badge_granted_by = p_user;
    update public.groups set admin_id = null where admin_id = p_user;
    update public.comments set parent_comment_id = null
     where user_id <> p_user
       and parent_comment_id in (select id from public.comments where user_id = p_user);
    -- A plain repost has nothing of its own; a post that only pointed here keeps its words.
    delete from public.posts
     where post_type = 'repost' and user_id <> p_user
       and original_post_id in (select id from public.posts where user_id = p_user);
    update public.posts set original_post_id = null
     where user_id <> p_user
       and original_post_id in (select id from public.posts where user_id = p_user);
    update public.harassment_flags set message_id = null
     where message_id in (select id from public.messages where sender_id = p_user);
    update public.trust_circles set members = array_remove(members, p_user) where p_user = any(members);
    update public.kids_account_applications set child_user_id = null where child_user_id = p_user;
    update public.kids_account_applications set reviewed_by = null where reviewed_by = p_user;
    update public.reports set reviewed_by = null where reviewed_by = p_user;
    update public.reports set reporter_id = null where reporter_id = p_user;
    update public.verification_applications set reviewed_by = null where reviewed_by = p_user;
    update public.withdrawals set decided_by = null where decided_by = p_user;
    update public.feedback set user_id = null where user_id = p_user;
    update public.group_activity_log set actor_id = null where actor_id = p_user;
    update public.group_admin_rules set created_by = null where created_by = p_user;

    -- Everything else that is the account's.
    delete from public.notifications where actor_id = p_user;
    delete from public.messages where sender_id = p_user;
    delete from public.shared_media where sender_id = p_user;
    delete from public.screenshot_events where user_id = p_user;
    delete from public.account_lock_events where user_id = p_user;
    delete from public.harassment_flags where reporter_id = p_user or reported_user_id = p_user;
    delete from public.gov_verification_requests where user_id = p_user;
    delete from public.child_activity_log where parent_id = p_user or child_id = p_user;
    delete from public.parent_approvals where parent_id = p_user or child_id = p_user;
    delete from public.parent_link_requests where parent_id = p_user or child_id = p_user;
    delete from public.call_signals where sender_id = p_user;
    delete from public.calls where caller_id = p_user or callee_id = p_user;
    delete from public.session_logs where user_id = p_user;
    delete from public.channels where owner_id = p_user;
    delete from public.post_views where viewer_id = p_user;
    delete from public.clip_views where viewer_id = p_user;
    delete from public.story_views where viewer_id = p_user
        or story_id in (select id from public.stories where user_id = p_user);
    delete from public.comments where clip_id in (select id from public.trustclips where user_id = p_user);
    delete from public.trustclips where user_id = p_user;
    delete from public.clip_likes where user_id = p_user;
    delete from public.clip_sticker_responses where user_id = p_user;
    delete from public.channel_followers where user_id = p_user;
    delete from public.follow_requests where requester_id = p_user or target_id = p_user;
    delete from public.group_member_prefs where user_id = p_user;
    delete from public.hide_story_from where owner_id = p_user or hidden_user_id = p_user;
    delete from public.live_sessions where user_id = p_user;
    delete from public.login_attempts where user_id = p_user;
    delete from public.recently_deleted_stories where user_id = p_user;
    delete from public.trust_circles where user_id = p_user;
    delete from public.user_locations where user_id = p_user;
    delete from public.verification_applications where user_id = p_user;
    delete from public.kids_account_applications where applicant_id = p_user;
    delete from public.watch_history where user_id = p_user;
    delete from public.wallets where user_id = p_user;

    -- The profile. Posts, comments, likes, follows, stories, notifications, keys,
    -- devices, Eddie chats and the rest go with it.
    delete from public.users where id = p_user;
    delete from public.profiles where id = p_user;

    return jsonb_build_object('ok', true, 'files', v_files);
end;
$$;

revoke all on function public.tf_delete_account(uuid) from public, anon, authenticated;
grant execute on function public.tf_delete_account(uuid) to service_role;

commit;

-- ---------------------------------------------------------------------------
-- CHECK (read-only)
-- ---------------------------------------------------------------------------
-- select has_function_privilege('authenticated', 'public.tf_delete_account(uuid)', 'execute') as users_can_call,
--        has_function_privilege('service_role', 'public.tf_delete_account(uuid)', 'execute') as server_can_call;
-- Expect false, true.

-- ---------------------------------------------------------------------------
-- ROLLBACK
-- ---------------------------------------------------------------------------
-- drop function if exists public.tf_delete_account(uuid);

-- ═══════════════════════════════════════════════════════════════════════════
-- report_attachments.sql
-- ═══════════════════════════════════════════════════════════════════════════
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
-- Applied to production: NOT YET. (Fill the date on apply.)

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

-- ═══════════════════════════════════════════════════════════════════════════
-- nearby_off.sql
-- ═══════════════════════════════════════════════════════════════════════════
-- Nobody's location is readable by anyone else while the map and Nearby are off.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it.
--
-- WHAT WAS WRONG
--
-- public.user_locations holds the live location the people map uploads. Its
-- read rules were "Anyone can read locations" (USING true, for every role,
-- signed out included) and "viewable by authenticated users". So any visitor
-- could ask the API for every shared location, and the app's "who can see my
-- location" setting was never enforced anywhere but on the phone. There were
-- also five overlapping rules for writing your own row.
--
-- THE FIX
--
-- The map and Nearby are switched off (TF_FEATURE_NEARBY), and the app no
-- longer uploads a location. Here: one rule, your own row only, for reading
-- and writing, and the table emptied because nothing should be kept while the
-- feature is off. It held 0 rows on 2026-10-18.
--
-- BEFORE SWITCHING NEARBY BACK ON: a SELECT rule that enforces who may see a
-- location (followers, close friends) has to exist in the database. "Anyone"
-- must never come back.
--
-- Applied to production: NOT YET. (Fill the date on apply.)

begin;

drop policy if exists "Anyone can read locations" on public.user_locations;
drop policy if exists "User locations are viewable by authenticated users" on public.user_locations;
drop policy if exists "Users can delete their own location" on public.user_locations;
drop policy if exists "Users can update their own location" on public.user_locations;
drop policy if exists "Users can upsert their own location" on public.user_locations;
drop policy if exists "users can upsert own location" on public.user_locations;
drop policy if exists "Users can manage their own location" on public.user_locations;
drop policy if exists "Own location only" on public.user_locations;

create policy "Own location only"
    on public.user_locations for all to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

delete from public.user_locations;

commit;

-- ---------------------------------------------------------------------------
-- CHECK (read-only)
-- ---------------------------------------------------------------------------
-- select policyname, cmd, roles::text, qual from pg_policies
--  where schemaname = 'public' and tablename = 'user_locations';
-- Expect one row: "Own location only".

-- ---------------------------------------------------------------------------
-- ROLLBACK: deliberately not provided for the "Anyone can read" rule. If the
-- map returns, write an audience rule instead (see above).
-- ---------------------------------------------------------------------------

-- ═══════════════════════════════════════════════════════════════════════════
-- marketplace_listings.sql
-- ═══════════════════════════════════════════════════════════════════════════
-- Marketplace listings: a post type with a few fixed facts the database checks.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it.
--
-- WHAT THIS ADDS
--
-- A listing is an ordinary post (description in text_content, photos in
-- media_urls) with post_type 'listing' and a small `listing` object:
--
--   { "category": "housing" | "for_sale" | "services" | "wanted",
--     "title": 1-80 characters,
--     "price": a number of rand from 0 to 10 000 000, or null for "talk to me",
--     "currency": "ZAR",
--     "area": up to 60 characters, optional,
--     "status": "available" | "sold" }
--
-- The database refuses any listing that does not have that shape, so a
-- category or price the app would not offer cannot be written by calling the
-- API directly. A post is a listing exactly when it has that object.
--
-- Nothing about who may post changes: the existing rule already requires a
-- verified account to create any post (tf_is_verified()), so every seller is
-- verified, and only the seller can edit or delete their listing, which is
-- how "mark as sold" works. TrustFirst takes no part in payment.
--
-- Applied to production: NOT YET. (Fill the date on apply.)

begin;

alter table public.posts drop constraint if exists posts_post_type_check;
alter table public.posts add constraint posts_post_type_check check (post_type = any (array[
    'text', 'image', 'video', 'poll', 'quiz', 'question', 'quote', 'repost',
    'thought', 'trustclip', 'album', 'gif', 'listing']));

alter table public.posts add column if not exists listing jsonb;

alter table public.posts drop constraint if exists posts_listing_shape;
alter table public.posts add constraint posts_listing_shape check (
    listing is null or (
        jsonb_typeof(listing) = 'object'
        and listing->>'category' in ('housing', 'for_sale', 'services', 'wanted')
        and length(coalesce(listing->>'title', '')) between 1 and 80
        and (coalesce(jsonb_typeof(listing->'price'), 'null') = 'null'
             or (jsonb_typeof(listing->'price') = 'number'
                 and (listing->>'price')::numeric between 0 and 10000000))
        and coalesce(listing->>'currency', 'ZAR') = 'ZAR'
        and length(coalesce(listing->>'area', '')) <= 60
        and coalesce(listing->>'status', 'available') in ('available', 'sold')
    )
);

alter table public.posts drop constraint if exists posts_listing_matches_type;
alter table public.posts add constraint posts_listing_matches_type
    check ((post_type = 'listing') = (listing is not null));

create index if not exists posts_listings_recent
    on public.posts (created_at desc) where post_type = 'listing';

commit;

-- ---------------------------------------------------------------------------
-- CHECK (read-only)
-- ---------------------------------------------------------------------------
-- select conname from pg_constraint
--  where conrelid = 'public.posts'::regclass and conname like 'posts_listing%';
-- Expect posts_listing_shape and posts_listing_matches_type.

-- ---------------------------------------------------------------------------
-- ROLLBACK (only while no listing has been posted; otherwise delete those
-- posts first, or the type rule will refuse to come back)
-- ---------------------------------------------------------------------------
-- begin;
-- drop index if exists public.posts_listings_recent;
-- alter table public.posts drop constraint if exists posts_listing_matches_type;
-- alter table public.posts drop constraint if exists posts_listing_shape;
-- alter table public.posts drop column if exists listing;
-- alter table public.posts drop constraint if exists posts_post_type_check;
-- alter table public.posts add constraint posts_post_type_check check (post_type = any (array[
--     'text', 'image', 'video', 'poll', 'quiz', 'question', 'quote', 'repost',
--     'thought', 'trustclip', 'album', 'gif']));
-- commit;

