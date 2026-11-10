# Højde platform — plan in Gær

Maps the canvas (`design/project/*.dc.html`) to Gær: tables, endpoints, pages and phases. Ported from surdej-v2's
`member-hojde` (P0–P2); where Surdej and Gær differ, Gær's rules win.

## From Surdej to Gær

| surdej-v2 (member-hojde) | Gær |
|---|---|
| Fastify worker behind the NATS gateway (`/api/module/member-hojde`) | `server/app/routes/hojde.py` under `/api/hojde` |
| Identity from gateway headers `x-user-id` | `current_user` → `app/hojde/access.py` (membership by e-mail at first login) |
| Super admin without membership = Højde administrator | None: `python -m app.hojde.admin add-staff`, audited |
| Prisma segment `member_hojde` (uuid ids) | `migrations/0022_hojde.sql`, `hojde_*` tables, bigserial ids |
| Names copied into checklist, findings, certificates | Only in `hojde_members`; other tables point at the member |
| Zod schemas | Pydantic models (`OrderIn`, `LocationIn`, `InviteIn`, `OrganizationIn`) |
| Core `AuditLog` (not always in the same transaction) | `audit()` in the same transaction |
| `POST /backoffice/weather/check` only | Also a job every hour (phase 3) |
| CommandRegistry + sidebar | `web/src/routes.json`, `chrome: "own"`, `feature: "hojde"`, nested under `/portal` |
| No feature flags | Feature `hojde` with rings in /admin/features |
| 2FA flag stored only | Enforced: `mfa_setup_required` / `stepup_required` |
| Invitations in the audit log only | E-mail through Gær's mail provider (job `hojde.invitation.mail`) |
| Tailwind classes `bg-hj-*`, shadcn/ui | `web/src/hojde/hojde.css` (tokens scoped to `.hj`), own components in `hojde/ui.tsx` |
| Archivo / IBM Plex fonts | Not loaded from a third party; system font fallbacks |

## Data

| Table | Personal data |
|---|---|
| `hojde_organizations` | No (CVR, billing address, EAN) |
| `hojde_members` | Yes — name, e-mail, certificates; export + anonymise (`app/hojde/gdpr.py`) |
| `hojde_locations` | Site contact (the customer's, removed with the organisation) |
| `hojde_services` | No |
| `hojde_orders` | Site contact; `created_by` / `quote_approved_by` point at members |
| `hojde_tasks`, `hojde_checklist_items` | Point at members (pilot, ready by, done by) |
| `hojde_flights` | Pilot (member). No retention policy yet |
| `hojde_equipment` | No |
| `hojde_compliance_documents` | Pilot certificates point at the member; reference cleared on erasure |
| `hojde_findings` | `approved_by` points at the member |

## Phases

| Phase | Content | Status |
|---|---|---|
| 0 | Fork up to date with gaer-base; specs copied | ✅ |
| 1 | Migration, access + second factor, rules, ops (numbering, planning, weather rule), GDPR, seed, admin CLI, `GET /api/hojde/me`, tests | ✅ |
| 2 | Portal: API (`routes/hojde_portal.py`: overview, locations, services, orders with approve, cancel, confirm access; organisation, invitations), 6 pages in `web/src/hojde/`, `routes.json` (feature `hojde`), landing on `/`, invitation e-mails as the job `hojde.invitation.mail`, webhooks `hojde.order.created` / `hojde.quote.approved` / `hojde.order.cancelled`, tests | ✅ |
| 3 | Backoffice: API (overview, staff, tasks per week, quote, plan, task: checklist, permit, ready, reschedule, flights, deliver; equipment; compliance), 5 pages (dark), weather job, webhooks `hojde.*`, events | — |
| 4 | Compare with `images/`, roll out (staff ring first), archive hoejde/surdej-v2 | — |
| P3–P5 | Data pipeline (uploads to Object Storage, jobs), delivery (reports, findings, share links under `/api/public`), business (invoices, CRM, website on `/w`) | — |

## Acceptance

- Phase 1: Mette (customer admin) and Emil (staff) sign in with a code and each get their membership linked —
  `server/tests/test_hojde.py`.
- Phase 2: Mette creates a location, orders an inspection, approves a quote and sees it on the overview —
  `server/tests/test_hojde_portal.py`, and run in a browser against the demo tenant.
- Phase 3: an order becomes a task, the checklist gates "Markér klar", and a logged flight shows in the logbook.

## Try it

```bash
docker compose up -d
cd server && python -m app.migrate && python -m app.hojde.seed
```

With `MAIL_PROVIDER=console`, sign in as `mh@kystparken.example` (customer admin) or `emil@hojde.example` (staff); the code is in the server log.
`GET /api/hojde/me` shows the membership and whether a second factor is needed.
