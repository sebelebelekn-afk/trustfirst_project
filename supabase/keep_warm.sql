-- Holding the app open, so nobody meets Render's "service waking up" page.
--
-- This is applied to the Supabase project, not to Django, so it does not run
-- itself from this repository. It is written down here because a scheduled job
-- that exists only inside a database is invisible: nobody reading this project
-- would know what is keeping the app awake, or where to look when it stops.
-- Re-running it is safe.
--
--
-- WHAT IT IS FOR
--
-- Render stops a free instance after 15 minutes without traffic and shows its
-- own branded holding page, for roughly a minute, to whoever knocks first.
-- That page belongs to Render and no code in this repository can suppress it.
-- What we can do is make sure the instance is never asleep when somebody
-- arrives. A request every five minutes does that.
--
--
-- WHY NOT GITHUB ACTIONS
--
-- It was tried first, in .github/workflows/keepwarm.yml, and it does not work.
-- GitHub's scheduled runs are best-effort: an hourly schedule fired at 17:34,
-- 20:28, 23:03 and 02:06 — every two and a half to three hours, leaving holes
-- of 90 to 120 minutes. Render spins down after 15. The app was asleep for most
-- of every gap, which is exactly the problem this was meant to solve.
--
-- pg_cron is a real scheduler and fires when it says it will. That workflow is
-- kept as a backup, since a public repository costs no Actions minutes, but
-- this is the one doing the work.
--
--
-- WHY IT SLEEPS AT ALL
--
-- Render allows 750 free instance-hours a month per workspace, and spun-down
-- time does not count against them. Running around the clock is 744 hours in a
-- 31-day month: it fits, with six hours to spare, which is not margin. Running
-- out suspends every free service until the 1st — a total outage, far worse
-- than one slow request.
--
-- Skipping 01:00-03:59 UTC costs about 656 hours a month and leaves 94 in hand.
-- The instance spins down around 01:10 UTC and is woken by the 04:00 ping, so
-- the gap is 03:10-06:00 in Johannesburg, which is the quietest slot available
-- for an audience that is mostly South African. During it the app still answers
-- every request; the first visitor simply pays for the wake-up instead of this
-- job, and any real visitor keeps it open for the next 15 minutes just as well.
--
-- ONE FREE SERVICE ONLY: the 750 hours belong to the workspace, not the
-- service. A second free web service halves the budget and both get suspended.
--
--
-- IF THE APP MOVES OFF RENDER
--
-- Change the URL below and drop the sleep window: on a host billed per request
-- rather than per hour an idle instance costs nothing. See cloudbuild.yaml.

create extension if not exists pg_net;

select cron.unschedule('keep-trustfirst-warm')
 where exists (select 1 from cron.job where jobname = 'keep-trustfirst-warm');

select cron.schedule(
  'keep-trustfirst-warm',
  '*/5 0,4-23 * * *',
  -- /healthz is the cheapest endpoint in the app: no database, no session, no
  -- template. See core/views.py.
  --
  -- The 60-second timeout matters more than it looks. pg_net defaults to five,
  -- and a spun-down instance takes closer to a minute to come back — so the
  -- first ping after a quiet spell, the one actually paying for the wake-up,
  -- was the one guaranteed to time out. It still reached Render and still woke
  -- it, but it recorded an error rather than a result, which would have made
  -- this job look broken every single morning. Once warm the same call answers
  -- in well under a second.
  $$select net.http_get(
      'https://trustfirst-project-bt1h.onrender.com/healthz',
      timeout_milliseconds => 60000
    )$$
);

-- Checking on it later:
--
--   select jobname, schedule, active from cron.job;
--   select status_code, error_msg, created
--     from net._http_response order by id desc limit 20;
--
-- A healthy row is status_code 200 with content {"ok": true}.
