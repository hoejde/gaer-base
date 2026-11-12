# Plan: flyt Højde fra surdej-v2 til Gær

Kilde: `hoejde/surdej-v2` (fork-punkt `5c203c2`, upstream PR #26). Mål: `hoejde/gaer-base`.
Arbejdsgang: `/gaer-mix` — én fase ad gangen, `pytest server` og `npm run build --prefix web` grønne efter hver.

**Ny rutestruktur i Gær (besluttet, laves i base):** appen skrives altid som **`app.domain.com`**, og websitet
ligger på **`domain.com`**. Appens forside `/` flyttes til **`/portal`**, og websitet `/w/…` flyttes til **`/`**.
Det er fase A, en generel platformændring i gaer-base, og den kommer før alt Højde-arbejdet.

## 1. Hvad er "custom" i surdej-v2

Alt efter fork-punktet: 13 commits, 197 filer, ~20.500 linjer. Sorteret:

| Del | Omfang | Flyttes? |
|---|---|---|
| `modules/member-hojde/` — shared (domæne, Zod-skemaer, regler, formatering), worker (Fastify, 19 Prisma-modeller, 2 migrationer, seed), ui-klient | ~7.500 linjer | **Ja** — kernen |
| `apps/frontend/src/domains/hojde/` — portal (6 sider), backoffice (17 sider), komponenter, tests | ~6.000 linjer | **Ja** |
| `domains/hojde/website/` + `vite-plugin-hojde-website.ts` — offentligt website da/en, SEO, sitemap, kontaktformular → CRM-lead | ~2.700 linjer | **Ja**, men skrives om (se B3) |
| `specs/hojde-platform/` — PLAN, README, Claude Design-canvas (34 artboards, design-tokens) | | **Ja** → `specs/hojde/` |
| `docs/images/hojde/` — 13 skærmbilleder | | **Ja** → `specs/hojde/images/` |
| `surdej.yaml`, `infra/k8s/*` — Azure/OVH MKS, `ghcr.io/hoejde`, `api/app.hoejde.dk` (GUID'er er stadig placeholders) | | **Nej** — erstattes af Gærs `deploy/` (fase 8) |
| Hjem-dashboard (`f49f63e`), Happy Mates-ikon/OG (`dcc7510`), RED-oprydning, port- og boot-fixes | | **Nej** — generiske Surdej-ændringer; Gær har sin egen forside, branding og OG |
| `member-database`, `member-useradmin` | | **Nej** — upstream Surdej-moduler; dækket af Gærs `/admin/users`, MFA og `/admin/data` (Udforsk) |

## 2. Oversættelse Surdej → Gær

| Surdej (Højde bruger) | Gær |
|---|---|
| Worker på NATS bag gatewayen (`/api/module/member-hojde/*`), `x-user-id` | FastAPI-routere i samme proces, `/api/hojde/*`, `current_user` → `Principal` |
| Prisma-segment `member_hojde`, 2 migrationer | Én ny SQL-migration `0022_hojde.sql`, tabeller `hojde_*`, psycopg + rå SQL |
| Zod-kontrakter (`schemas.ts`, 1.071 linjer) | Pydantic-modeller i Python; TS-typer i `web/src/hojde/types.ts` |
| `rules.ts` (håndhævet i workeren) | `server/app/hojde/rules.py` (serveren håndhæver); `hojde.test.ts` → pytest |
| `public."AuditLog"` (resource `hojde`) | `logs.audit(conn, …)` i samme transaktion (skill `gaer-audit`) |
| Platform-blob-store (`fileBlobId`) | Object Storage via `storage.py`/`uploads.py`; dokumenter i filtræet under `/shared/hojde/…` |
| Super admin uden staff-medlemskab = Højde-administrator | Gær `admin`-rolle (samme regel) |
| `Organization.require2fa` (kun gemt, ikke håndhævet) | Håndhæves: medlemmer af en sådan organisation får "Kræv passkey" (strammer, omgår intet) |
| Kommando-registry, ⌘K, sidebar-config | `web/src/routes.json` + `<Route>` i `App.tsx`, `chrome: "own"` for portal/backoffice |
| Kundeportal `/portal/*`, backoffice `/backoffice/*` | Samme stier: `/portal` er nu appens forside (fase A), så kunder lander direkte på Højde-overblikket |
| Website `/da/…`, `/en/…` (SPA) | Website på `/` og `/<slug>` (server-renderet, fase A + 5) |
| Tailwind (`bg-hj-*`, ~540 className'r) + shadcn | Plain CSS: `web/src/hojde/hojde.css` med `--hj-*`-tokens under `.hojde` |
| `publicRoutes` + egen rate-limit/honeypot | `/api/public/hojde/leads` + Gærs proof-of-work-captcha, samtykke, rate-limit |
| Manuel `POST /backoffice/weather/check` | Job `hojde.weather_check` i `job_schedules` (+ knappen bevares) |
| "Ingen feature flags" | Feature-nøgle `hojde` i `features_catalog.py` + `<FeatureGate>` |

## 3. Beslutninger før start

- **B1 · Data:** Surdej-instansen er ikke i drift (placeholder-GUID'er i `surdej.yaml`). Forslag: ingen datamigrering — kun seed. *Bekræft.*
- **B2 · Ruter (besluttet):** `/portal` er appens forside for alle. For Højde viser den kundens overblik;
  kundesiderne ligger under `/portal/…` (`/portal/lokationer`, `/portal/bestillinger`, `/portal/organisation`).
  Personale sendes fra `/portal` til `/backoffice/…`. Brugere uden Højde-medlemskab ser Gærs normale forside
  (klip, filer osv.). Backoffice ligger ikke i `/admin`, da Højde-personale ikke er platform-admins.
- **B3 · Website (besluttet):** websitet ligger på `/`. Højde-websitet bygges som en kodet forside-variant ved
  siden af "Facit · 246" (`web_front = "hojde"`), server-renderet i Python med indholdet fra `content.ts` →
  `hojde/website_content.py`. Undersider på `/<slug>`, sprog via `?lang=` + cookie som i dag.
- **B4 · Domæner (besluttet):** princippet er altid `app.domain.com` for appen og `domain.com` for websitet,
  begge fra samme container (fase A). For Højde: `app.hoejde.dk` er appen (`ORIGIN`), `hoejde.dk` og `hoejde.eu`
  er website-værter (`SITE_HOSTS`). `/` vælger sprog efter vært (dk → da, eu → en), og canonical/hreflang følger
  værten. `app.hoejde.dk/` sender til `/portal`.
- **B5 · Afhængigheder:** Tilføj `leaflet`/`react-leaflet` (kort) og `recharts` (statistik) til `web/` — eller tegn graferne selv i SVG for at holde Gær let. Forslag: leaflet ja, recharts erstattes af små SVG-grafer.

## 4. Faser (én PR hver)

### Fase A — Gær i base: `app.domain.com` + website på `domain.com`
Generel platformændring i gaer-base (ingen Højde-kode). Højde-forken får den ved næste opdatering.

**Princip:** appen skrives altid `app.domain.com`; websitet ligger på `domain.com`. Samme container svarer på
begge værter og vælger flade efter `Host`.

| Vært | `/` | `/<slug>` | App-stier (`/portal`, `/login`, `/klip`, `/admin`, …) | Server-stier (`/api`, `/mcp`, `/.well-known`, `/health`) |
|---|---|---|---|---|
| `app.domain.com` (`ORIGIN`) | 302 → `/portal` | 308 → `domain.com/<slug>` | appen | svarer |
| `domain.com` (+ `SITE_HOSTS`) | websitet | website-side eller 404 | 308 → `app.domain.com/<sti>` | svarer (websitets `/api/public`, `/api/collect`) |
| Én vært (lokalt, eller `SITE_ORIGIN` = `ORIGIN`) | websitet | website-side | appen | svarer |

Gamle stier: `/w` og `/w/<slug>` → 308 til `/` og `/<slug>` på website-værten, så eksisterende links virker.

Konfiguration
- [ ] `config.py`: `ORIGIN` er fortsat appens adresse (`https://app.domain.com`) og bruges til alle links, Gær
      danner (mails, MCP, OAuth, deep links, udvidelsen). Ny `SITE_ORIGIN` (standard: `ORIGIN` uden `app.`
      foran; lig `ORIGIN` når der ikke er noget `app.`) og `SITE_HOSTS` (ekstra website-værter, kommasepareret)
- [ ] `RP_ID` (passkeys) forbliver appens vært; session-cookien er værtsbunden til `app.domain.com`
- [ ] `deploy/app.env.example`, `.env.example`, `deploy/compose.yml`: cloudflared ruter både `domain.com` og
      `app.domain.com` til containeren; `gaer-init`/`gaer-dev` beskriver det

Server
- [ ] `routes.json`: `/` → `server`, adgang `public` (website); ny `/portal` → `app`, adgang `user`;
      `/w/{slug}` → `/{slug}`; kør `npm run app-map --prefix web` (genererer `server/app/routes.json`,
      `mcp/app_map.json` og rutetabellerne i `instructions.md` og `README.md`)
- [ ] Ny `app/hosts.py`: `surface(request) → "app" | "site" | "both"` ud fra `Host` mod `ORIGIN`, `SITE_ORIGIN`
      og `SITE_HOSTS`. Redirects bygges altid fra de konfigurerede adresser, aldrig fra `Host`. Ukendte værter
      behandles som appen
- [ ] `main.py`: vært-routing i `spa()` efter tabellen ovenfor; `/portal` serveres af SPA'en, og anonyme på
      `/portal` sendes til `/login?next=/portal`
- [ ] Rækkefølge på website-værten: kendt rute i manifestet → statisk fil → website-side (`/<slug>`) → websitets
      404. SPA'en svarer ikke længere på ukendte stier der
- [ ] `routes/web.py`: router på `/` og `/{slug:path}` (registreres sidst); `/w` og `/w/{slug}` → 308.
      Statiske filer på `/static/w/…` (gamle `/w/static/…` → 308)
- [ ] Reserverede slugs: `/admin/web` afviser slugs, der rammer en rute i manifestet (`login`, `portal`, `klip`,
      `filer`, `konto`, `user`, `privatliv`, `api`, `mcp`, `m`, `extension`, `admin`, `health`, `static`,
      `assets`, …); en migration omdøber eksisterende kollisioner
- [ ] Website-links: "Log ind" og login-kortet peger på `ORIGIN/login`; `web_front.py`, `web.py`, `og.py`:
      canonical, hreflang og og:url på `SITE_ORIGIN` uden `/w`; app-sider (`app_html`) bruger `ORIGIN`
- [ ] `/privatliv` er en app-side og ligger på `app.domain.com`; websitets footer linker dertil. Samtykke-
      cookien er pr. vært, så banneret kan vises på begge — acceptabelt, noteres i docs
- [ ] CSP pr. sti (`csp_for`): websitets politik på website-værten; appens politik på app-værten
- [ ] `ai.py`: klientværktøjets stiliste (`/w/` → `SITE_ORIGIN/`, forsiden → `/portal`)
- [ ] Login: standard-`next` er `/portal`; logout sender til `SITE_ORIGIN/`
- [ ] `/go` deep links: standardsti `/portal`

Web
- [ ] `App.tsx`: `<Route path="/portal">` for `Home`; catch-all `*` → `/portal`; brand-link og logout
- [ ] `shell.tsx`: brand-links `/` → `/portal`; "Offentlig side" → websitets adresse (fra `/api/public/config`,
      nyt felt `site_url`)
- [ ] `admin-app` (`main.tsx`, `mfa.tsx`, `AdminShell.tsx`): "Til appen" → `/portal`; `pages/Web.tsx`: side-URL'er
      på `site_url` uden `/w`
- [ ] Mobil (`/m`), udvidelse (`/extension`) og Office ligger på app-værten og berøres ikke; tjek links til `/`

Data og tests
- [ ] Adoption: migration, der omskriver forløbstrin `/` → `/portal` (besøg er historik og bliver stående)
- [ ] Opdatér `test_integrations.py`, `test_og.py`, `test_routes.py`, `test_auth.py`, `test_ai.py`,
      `test_adoption.py`
- [ ] Nye tests (`test_hosts.py`): hver celle i tabellen ovenfor, redirects fra `/w/…`, at redirects ignorerer en
      forfalsket `Host`, reserverede slugs, 404 på website-værten, én-værts-tilstanden
- [ ] Docs: `instructions.md` (rutetabellen, reglen "offentligt indhold ligger under `/w/`…" → "på website-værten",
      og princippet `app.domain.com`), skills `gaer-integrations` og `gaer-backend`, `README.md`

### Fase 0 — Specs og skelet
- [ ] Kopiér `specs/hojde-platform/` → `specs/hojde/` (+ skærmbilleder); omskriv PLAN til Gær-termer (denne tabel i §2)
- [ ] Feature-nøgle `hojde` i `features_catalog.py`
- [ ] Mappe `server/app/hojde/` (`access.py`, `rules.py`, `providers.py`, `seed.py`) og `web/src/hojde/`

### Fase 1 — Data og adgang (P0)
- [ ] `0022_hojde.sql`: alle 19 modeller som `hojde_*`-tabeller, `hojde_members.user_id → users.id`, invitation = medlem med status `inviteret`
- [ ] `hojde/access.py`: slå medlemskab op (user id, ellers e-mail → link ved første login, 7-dages invitationer), `require_hojde_staff(roles…)`, `require_hojde_customer()`, lokations-scope
- [ ] `rules.py` + pytest-port af `hojde.test.ts` (readiness, vejr, 24 t-afbestilling, risikoscore, 72 t-rapport, audit-lukning, leads, kort ≥ 30 fotos, sidste administrator)
- [ ] GDPR: `hojde_members`, `hojde_leads`, kontaktpersoner på lokationer i `gdpr.py` (eksport + sletning)
- [ ] `retention_policies` for leads (tabte/gamle) og vejrdata, hvis de vokser

### Fase 2 — Portal (P1)
- [ ] `routes/hojde_portal.py`: overview, organisation (+ invitationer, resend, (de)aktiver), lokationer, services, ordrer (approve, cancel, confirm-access)
- [ ] Sider: Overblik, Lokationer, Lokation, Bestillinger, Ny bestilling (4 trin), Organisation; `Shell` + `ui.tsx` + `hojde.css` (lyst tema)
- [ ] Landing på `/portal`: Højde-kunder ser portaloverblikket, personale sendes til `/backoffice`, andre ser
      Gærs normale `Home` (`useHojdeLanding`)
- [ ] Tests: `server/tests/test_hojde_portal.py`

### Fase 3 — Backoffice: drift (P2 + v2 Drift)
- [ ] `routes/hojde_backoffice.py` (+ `hojde_operations.py`): overview/statistik, ordrer, tidslinje, opgaver, opgave (tjekliste, tilladelse, klar, flyt, flyvninger, levér), udstyr, flyvelog + CSV, kortlægning
- [ ] `providers.py`: deterministiske vejr-/zone-stubs; job `hojde.weather_check`; kort-status-stub
- [ ] Sider: Overblik (I dag · Statistik · Lokationer/kort), Ordrer, Tidslinje, Opgaver, Opgave, Udstyr, Flyvelog, Kortlægning (mørkt tema)

### Fase 4 — Backoffice: sikkerhed, personer, aktiver (v2)
- [ ] `routes/hojde_safety.py`: risici, hændelser (EU 376/2014, 72 t), audits, vedligehold
- [ ] `routes/hojde_people.py`: CRM (konverter lead → kunde + invitation), kunder, team
- [ ] `routes/hojde_assets.py`: dokumentbibliotek med versioner/udløb, filer via Object Storage
- [ ] Live-tællere i sidenavigationen
- [ ] Webhook-events `hojde.lead.created`, `hojde.incident.reportable` i `webhooks.EVENTS` (ids, ingen persondata)

### Fase 5 — Website og kontaktformular (P5-website)
- [ ] `web_front`-variant `hojde` på `/` (forside, ydelser, brancher, platform, priser, om, kontakt, privatliv),
      da/en, sprog efter vært (B4); undersider på `/<slug>`
- [ ] hreflang, JSON-LD (Organization, BreadcrumbList, Service, FAQPage), `sitemap.xml` + `robots.txt` fra serveren
- [ ] `POST /api/public/hojde/leads`: captcha, samtykke, honeypot, rate-limit → `hojde_leads`, audit
- [ ] og:image pr. side (`og.py`, `brand-assets.cjs`)

### Fase 6 — Seed og demo
- [ ] `python -m app.hojde.seed`: demo-tenant (Kystparken, Mette Holm, Emil …) relativt til i dag; nægter i produktion
- [ ] Indgang i `/gaer-dev`

### Fase 7 — MCP (valgfri)
- [ ] Udvalgte læseværktøjer i `/mcp` (mine ordrer, lokationer) og i `/mcp/admin` (opgaver, hændelser) via `mcp/toolmap.py`

### Fase 8 — Drift og cut-over
- [ ] `deploy/.env` + `app.env` for Højde: `ORIGIN=https://app.hoejde.dk`, `SITE_ORIGIN=https://hoejde.dk`,
      `SITE_HOSTS=hoejde.eu`, `RP_ID=app.hoejde.dk`, Object Storage-bucket, mail-afsender, `BOOTSTRAP_ADMIN_EMAIL`
- [ ] cloudflared-hostnames for `app.hoejde.dk`, `hoejde.dk`, `hoejde.eu`; GitHub-secrets til `deploy.yml`
- [ ] Branding: `app_name`, logo og farver via `/admin/settings`
- [ ] Smoke: kunde og medarbejder lander hver i deres shell; ordre → tilbud → godkend → planlæg → opgave → klar → flyvning → levér
- [ ] Arkivér `hoejde/surdej-v2` (read-only) når Gær kører

## 5. Hold forken let at opdatere fra gaer-base

Højde-koden ligger i egne filer (`server/app/hojde/`, `routes/hojde_*.py`, `web/src/hojde/`, `specs/hojde/`). Kun få
fælles filer røres: `main.py` (registrér routere), `App.tsx` og `routes.json`, `features_catalog.py`, `gdpr.py`,
`retention.py`, `webhooks.py`, `web_front.py`. Migrationsnumre: tag næste ledige ved hver merge fra gaer-base.

## 6. Risici

- **Port-omfang:** ~3.500 linjer TS-worker → Python. Reglerne (`rules.ts`) er det vigtigste at få 1:1 — port testene først.
- **Tailwind → CSS:** største frontend-arbejde; tokens findes allerede i `specs/hojde-platform/design/project/ds/hojde/tokens.css`.
- **Fase A rammer hele platformen:** website-slugs på roden kan kollidere med app-ruter, og alle eksterne links til
  `/w/…` og `/` (mails, MCP-deep links, bogmærker) skal fortsat virke via redirects. Eksisterende instanser, der
  i dag kører appen på `domain.com`, skal flytte `ORIGIN` til `app.domain.com` og registrere passkeys igen, hvis
  `RP_ID` ændres. Indtil de gør det, kører de i én-værts-tilstand, så intet går i stykker ved opdateringen.
- **Rolle-model:** Højde-roller (administrator, analytiker, pilot, kundeansvarlig, kundeadmin, kundebruger) lever i
  `hojde_members`, ikke i Gærs admin-roller — staff skal ikke have adgang til `/admin`.
