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
-- WHY IT SLEEPS AT ALL, AND WHY THESE PARTICULAR HOURS
--
-- Render allows 750 free instance-hours a month per workspace, and spun-down
-- time does not count against them. Running around the clock is 744 hours in a
-- 31-day month: it fits, with six hours to spare, which is not margin. Running
-- out suspends every free service until the 1st — a total outage, far worse
-- than one slow request.
--
-- So something has to sleep, and the hours were guessed the first time. They
-- were wrong: the window ran to 06:00 in Johannesburg and somebody using the
-- app at 04:00 met the waking-up page, which is the exact thing this exists to
-- prevent.
--
-- They are no longer guessed. Grouping login_activity and trusted_devices by
-- hour of the day in Johannesburg time gives the real shape, and it is busy
-- almost everywhere: peaks at 14:00 and 21:00, real traffic through the
-- evening, and something happening in nearly every hour of the night. The only
-- two consecutive hours with no recorded activity at all are 05:00 and 06:00.
--
-- So that is the window, and only that:
--
--   pings   05:00-02:55 UTC every 5 minutes, plus one at 04:45
--   asleep  roughly 03:10-04:45 UTC  =  05:10-06:45 SAST
--   usage   about 695 hours a month, leaving ~55 in hand
--
-- The 04:45 ping is a second job on purpose. Without it the first knock would
-- land at 05:00 UTC, which is 07:00 SAST — the hour activity picks back up —
-- and the first person of the morning would pay for the wake-up instead of the
-- scheduler. Waking fifteen minutes early costs nothing and moves that cost off
-- a person.
--
-- Re-check this if usage changes. The query behind it:
--
--   select extract(hour from (created_at at time zone 'Africa/Johannesburg')) as h,
--          count(*) from public.login_activity group by h order by h;
--
-- ONE FREE SERVICE ONLY: the 750 hours belong to the workspace, not the
-- service. A second free web service halves the budget and both get suspended.
--
-- AND IF THERE IS EVER NO QUIET HOUR, this stops working and no schedule will
-- save it: an app busy around the clock needs 744 hours and has six to spare,
-- which is not a thing to run a business on. That is the point to leave the
-- free tier, and cloudbuild.yaml is already written for it.
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
  '*/5 0-2,5-23 * * *',
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


-- The early knock, fifteen minutes before the main schedule resumes, so the
-- instance is already up when Johannesburg starts its day rather than the first
-- visitor paying for it. Separate job because pg_cron takes one schedule each.
select cron.unschedule('keep-trustfirst-warm-predawn')
 where exists (select 1 from cron.job where jobname = 'keep-trustfirst-warm-predawn');

select cron.schedule(
  'keep-trustfirst-warm-predawn',
  '45 4 * * *',
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
