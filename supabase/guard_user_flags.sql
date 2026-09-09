-- A badge nobody can award themselves.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it. Written down here because it is the rule that makes a verification
-- badge mean anything, and a trigger that exists only inside a database is
-- invisible to everyone reading the code that depends on it. Re-running is safe.
--
--
-- WHAT WAS WRONG
--
-- lock_down_users_columns.sql took away the two columns that led to money —
-- is_admin and coins — and deliberately left these, because the app writes them
-- from the browser and revoking the grant would have broken working screens:
--
--     verified, badge_status, badge_tier, trust_score, gov_verified,
--     face_verified, id_verified, liveness_verified, is_locked
--
-- Left as they were, any signed-in user could set them on their own row. That
-- means awarding yourself the blue tick, the gold badge, a government
-- verification, a perfect trust score — every mark this app displays to say a
-- person has been checked — on a platform whose entire proposition is that the
-- mark means somebody checked. It also meant anybody an admin locked could
-- unlock themselves, which is moderation that lasts until the person objects.
--
--
-- WHY A TRIGGER RATHER THAN REVOKING THE COLUMNS
--
-- Because the honest owners of these columns are not a role, they are a
-- circumstance. The same UPDATE is legitimate from an admin and forgery from
-- its subject, and grants cannot tell those apart — they only know which role
-- you are, and admins and ordinary users are both `authenticated`.
--
-- Revoking would have meant a new server endpoint for every admin action that
-- writes them, and rewriting admin.js to call them. A trigger asks the one
-- question that actually decides it — who is doing this, and to whom — and
-- leaves every existing screen working unchanged.
--
-- Three cases, in order:
--
--   auth.uid() is null   Not a browser. The Django server holds the service key
--                        (submit_liveness writes liveness_verified this way)
--                        and the coin functions are SECURITY DEFINER. Allowed.
--
--   is_admin()           Moderating is what being an admin is for. Allowed, and
--                        trustworthy now that is_admin itself cannot be
--                        self-granted — which is why the other file had to come
--                        first. Without it this check asks a question the
--                        attacker answers.
--
--   anyone else          May lock their own account, may not unlock it, and may
--                        not touch a verification flag at all.

create or replace function public.tf_guard_user_flags()
returns trigger
language plpgsql
security definer
set search_path to 'public'
as $$
begin
    if auth.uid() is null then
        return new;
    end if;

    if public.is_admin() then
        return new;
    end if;

    -- Locking your own account is yours to do. Unlocking it is not, or anyone
    -- an admin locks simply unlocks themselves.
    if new.is_locked is distinct from old.is_locked then
        if old.is_locked and not new.is_locked then
            raise exception 'only an admin can unlock an account';
        end if;
        if new.id is distinct from auth.uid() then
            raise exception 'you can only lock your own account';
        end if;
    end if;

    if new.verified              is distinct from old.verified
    or new.badge_status          is distinct from old.badge_status
    or new.badge_tier            is distinct from old.badge_tier
    or new.trust_score           is distinct from old.trust_score
    or new.gov_verified          is distinct from old.gov_verified
    or new.face_verified         is distinct from old.face_verified
    or new.id_verified           is distinct from old.id_verified
    or new.liveness_verified     is distinct from old.liveness_verified
    or new.liveness_steps        is distinct from old.liveness_steps
    or new.verification_method   is distinct from old.verification_method
    or new.gold_badge_reason     is distinct from old.gold_badge_reason
    or new.gold_badge_granted_by is distinct from old.gold_badge_granted_by
    or new.gold_badge_granted_at is distinct from old.gold_badge_granted_at
    then
        raise exception 'verification and badge flags are granted by review, not by their subject';
    end if;

    return new;
end;
$$;

drop trigger if exists tf_guard_user_flags on public.users;
create trigger tf_guard_user_flags
before update on public.users
for each row execute function public.tf_guard_user_flags();


-- VERIFIED AFTER APPLYING, every case rolled back:
--
--   as an ordinary user, on their own row
--     self-award badge     BLOCKED
--     self-set trust_score BLOCKED
--     lock own account     allowed
--     unlock own account   BLOCKED
--     edit bio and avatar  allowed
--
--   as an admin
--     grant a badge to another user   allowed
--     unlock another user's account   allowed
--
--   with no JWT, as the Django server
--     write liveness_verified         allowed
