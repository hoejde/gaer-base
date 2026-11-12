-- The app moves from / to /portal, and the public website from /w/… to / and /<slug> (app/hosts.py).
-- In production the app lives on app.<domain> (ORIGIN) and the website on <domain> (SITE_ORIGIN).

-- 1. A website page's address is now a path on the root, so it may not be one the app or the server answers
--    (routes/web.py RESERVED_SLUGS, checked again when a page is saved). Rename the few that would collide.
update web_pages p
set slug = case
        when exists (select 1 from web_pages q where q.slug = p.slug || '-side' and q.lang = p.lang)
        then p.slug || '-side-' || p.id
        else p.slug || '-side'
    end,
    updated_at = now()
where p.slug in ('admin', 'api', 'assets', 'develop', 'extension', 'filer', 'forbind', 'go', 'godkend', 'health',
                 'klip', 'konto', 'login', 'm', 'mcp', 'office-addin', 'portal', 'privatliv', 'static', 'user', 'w');

-- 2. Adoption: the home page was "/" and is now "/portal". Steps that measured it, and the visits they count,
--    follow it so existing journeys keep their numbers.
update adoption_steps set pattern = '/portal' where match_type = 'exact' and pattern = '/';
update adoption_visits set path = '/portal' where path = '/';
