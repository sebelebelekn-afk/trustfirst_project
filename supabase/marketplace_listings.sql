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
-- Applied to production: 2026-10-18, pasted into the Supabase SQL editor by the
-- owner (paste_in_order_2026-10-18.sql) and checked the same day against
-- pg_policies, pg_proc and storage.buckets.

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
