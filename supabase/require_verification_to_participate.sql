-- Only verified people can post, comment, like, follow, repost or start a chat.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it. Written down here because an access rule that lives only inside a
-- database is invisible to everyone reading this project, and this one is the
-- whole promise the product is built on.
--
-- WHAT WAS WRONG
--
-- The app tells people "only verified accounts can post, comment or start a
-- chat", and feed.js enforces exactly that in canPerformAction(). But the
-- browser talks straight to PostgREST with the anon key, so a check that only
-- lives in feed.js is a locked door with the window left open: anyone who skips
-- the app and calls the REST endpoint directly posts, comments, likes, follows
-- and messages as an unverified account. The RLS INSERT policies only ever
-- checked ownership (auth.uid() = user_id), never verification. The one claim
-- the brand rests on was not enforced where it had to be.
--
-- THE FIX
--
-- A small SECURITY DEFINER predicate, tf_is_verified(), reads the caller's own
-- users.verified, and it is added to the WITH CHECK of every INSERT the product
-- gates. SECURITY DEFINER so it can read the row regardless of who is asking;
-- it reveals nothing (a plain yes/no about yourself). For anon there is no
-- auth.uid(), so it returns false and the insert is refused, which is correct.
--
-- THE ONE DELIBERATE EXCEPTION: replying to a DM while unverified.
--
-- The product lets an unverified person REPLY in a conversation a verified
-- person opened with them, but never START one. That rule needs no verified
-- check on messages, and must not have one, or the reply breaks. It falls out
-- of the structure instead: starting a chat means INSERTing a conversation and
-- its participants, and those two are now gated on verification, so an
-- unverified account can never create a conversation. Any conversation it is a
-- participant of was therefore opened by a verified user, and msg_insert
-- already restricts a sender to conversations it belongs to (my_conv_ids()).
-- So messages is left exactly as it was. This mirrors _canSendDM() in feed.js.
--
-- WHAT IS NOT TOUCHED
--
--   * messages        -- the reply exception above.
--   * Eddie's own posts via /api/eddie/post/ -- that path uses the service key
--                        and is a system actor, not a user; it is meant to
--                        bypass RLS and is unaffected by these policies.
--   * every SELECT/UPDATE/DELETE -- this only governs creating new content.
--
-- Reviewed against pg_policies on 2026-10-18. Existing conditions below are
-- copied verbatim from the live policies; the only addition is the trailing
-- AND public.tf_is_verified().
--
-- Applied to production: NOT YET — pending review. (Fill the date on apply.)

begin;

-- The predicate. Owns nothing, reveals nothing but your own verified bit.
create or replace function public.tf_is_verified()
returns boolean
language sql
stable
security definer
set search_path to 'public'
as $$
  select coalesce(
    (select u.verified from public.users u where u.id = (select auth.uid())),
    false
  )
$$;

revoke all on function public.tf_is_verified() from public;
grant execute on function public.tf_is_verified() to anon, authenticated;

-- posts -- there were two identical INSERT policies ("Users can insert own
-- posts" and "Users create posts"). Permissive policies are OR'd, so gating one
-- and leaving the other would be no gate at all. Collapse to a single policy.
drop policy if exists "Users can insert own posts" on public.posts;
drop policy if exists "Users create posts" on public.posts;
create policy "Users create posts" on public.posts
  for insert to public
  with check (
    ((select auth.uid()) = user_id)
    and public.tf_is_verified()
  );

-- comments
drop policy if exists "Users comment" on public.comments;
create policy "Users comment" on public.comments
  for insert to public
  with check (
    ((select auth.uid()) = user_id)
    and (not tf_blocked(tf_post_author(post_id)))
    and ((clip_id is null) or (not tf_blocked(tf_clip_author(clip_id))))
    and public.tf_is_verified()
  );

-- likes
drop policy if exists "Users like" on public.likes;
create policy "Users like" on public.likes
  for insert to public
  with check (
    ((select auth.uid()) = user_id)
    and (not tf_blocked(tf_post_author(post_id)))
    and public.tf_is_verified()
  );

-- follows
drop policy if exists "Users follow" on public.follows;
create policy "Users follow" on public.follows
  for insert to public
  with check (
    ((select auth.uid()) = follower_id)
    and (not tf_blocked(following_id))
    and public.tf_is_verified()
  );

-- bookmarks
drop policy if exists "Users bookmark" on public.bookmarks;
create policy "Users bookmark" on public.bookmarks
  for insert to public
  with check (
    ((select auth.uid()) = user_id)
    and (not tf_blocked(tf_post_author(post_id)))
    and public.tf_is_verified()
  );

-- reposts -- an ALL policy. Leave USING (who may see/remove their own repost)
-- alone; gate only creation, in WITH CHECK.
drop policy if exists "Own reposts" on public.reposts;
create policy "Own reposts" on public.reposts
  for all to public
  using ((select auth.uid()) = user_id)
  with check (
    ((select auth.uid()) = user_id)
    and (not tf_blocked(tf_post_author(post_id)))
    and public.tf_is_verified()
  );

-- conversations -- "start a chat". Gating creation here is what preserves the
-- unverified-reply exception for messages (see the header).
drop policy if exists "conv_insert" on public.conversations;
create policy "conv_insert" on public.conversations
  for insert to public
  with check (
    (created_by = (select auth.uid()))
    and public.tf_is_verified()
  );

-- conversation_participants -- adding people to a chat you started. The check
-- is on the CREATOR (auth.uid()), so a verified starter may still add an
-- UNVERIFIED recipient; the recipient's own verified state is never required
-- here, which is what lets a verified user open a chat with anyone.
drop policy if exists "cp_insert" on public.conversation_participants;
create policy "cp_insert" on public.conversation_participants
  for insert to public
  with check (
    (conversation_id in (
       select conversations.id from conversations
       where conversations.created_by = (select auth.uid())
    ))
    and (not tf_blocked(user_id))
    and public.tf_is_verified()
  );

commit;

-- ---------------------------------------------------------------------------
-- ROLLBACK (restores the pre-change policies exactly; run if needed)
-- ---------------------------------------------------------------------------
-- begin;
-- drop policy if exists "Users create posts" on public.posts;
-- create policy "Users can insert own posts" on public.posts for insert to public
--   with check ((select auth.uid()) = user_id);
-- create policy "Users create posts" on public.posts for insert to public
--   with check ((select auth.uid()) = user_id);
-- drop policy if exists "Users comment" on public.comments;
-- create policy "Users comment" on public.comments for insert to public
--   with check (((select auth.uid()) = user_id) and (not tf_blocked(tf_post_author(post_id)))
--     and ((clip_id is null) or (not tf_blocked(tf_clip_author(clip_id)))));
-- drop policy if exists "Users like" on public.likes;
-- create policy "Users like" on public.likes for insert to public
--   with check (((select auth.uid()) = user_id) and (not tf_blocked(tf_post_author(post_id))));
-- drop policy if exists "Users follow" on public.follows;
-- create policy "Users follow" on public.follows for insert to public
--   with check (((select auth.uid()) = follower_id) and (not tf_blocked(following_id)));
-- drop policy if exists "Users bookmark" on public.bookmarks;
-- create policy "Users bookmark" on public.bookmarks for insert to public
--   with check (((select auth.uid()) = user_id) and (not tf_blocked(tf_post_author(post_id))));
-- drop policy if exists "Own reposts" on public.reposts;
-- create policy "Own reposts" on public.reposts for all to public
--   using ((select auth.uid()) = user_id)
--   with check (((select auth.uid()) = user_id) and (not tf_blocked(tf_post_author(post_id))));
-- drop policy if exists "conv_insert" on public.conversations;
-- create policy "conv_insert" on public.conversations for insert to public
--   with check (created_by = (select auth.uid()));
-- drop policy if exists "cp_insert" on public.conversation_participants;
-- create policy "cp_insert" on public.conversation_participants for insert to public
--   with check ((conversation_id in (select conversations.id from conversations
--       where conversations.created_by = (select auth.uid()))) and (not tf_blocked(user_id)));
-- drop function if exists public.tf_is_verified();
-- commit;
