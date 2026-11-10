# Højde platform

**Status:** In progress — phases 1–3 built in Gær (data, access, rules; the customer portal on `/portal`; the backoffice on `/backoffice`); rollout (phase 4) next
**Source:** Claude Design canvas "Højde-platformen — skærmbilleder" (32 screens + handover brief), exported 24.10.2026.
First built as the module `member-hojde` in hoejde/surdej-v2 (commit `dc00be2`, P0–P2) and moved to Gær from there.

## Purpose

Højde flies drones for building owners, contractors, energy, events, agriculture and forestry, and turns the data into
decisions. Customers follow their buildings and sites over time, order flights, approve quotes and see analyst-approved
AI findings in a customer portal (`/portal`). Højde's staff plan tasks, prepare flights legally (zone permits, weather,
checklists, equipment), keep the logbook and compliance documents, and — in later phases — run the data pipeline,
quality control and reporting in a backoffice (`/backoffice`).

## Source material

- `design/project/` — the canvas export as delivered: one `*.dc.html` per artboard, `canvas.json`, `ds/hojde/`
  (the Højde design system: tokens and five components) and `proto.css`. The screens are the source of truth for copy
  and layout. `Handover.dc.html` is the original brief, written for surdej-v2; where it names Surdej's stack (NATS,
  Prisma, feature flags off), [PLAN.md](PLAN.md) says what Gær uses instead.
- `images/` — screenshots of the v1 pages running in surdej-v2 against the demo tenant, to compare the Gær pages with.

## Decisions (10.11.2026)

- Login is Gær's e-mail + code + passkey. No Microsoft or Google sign-in.
- The backoffice lives in the app on `/` under `/backoffice`, not in `/admin`. Pilots and analysts are not Gær admins.
- No data is moved from surdej-v2 (it only held demo data). The demo tenant comes from `python -m app.hojde.seed`.
- Staff always need a second factor; customers when their organisation has `require_2fa`.

## Open questions

- How long must the flight log and compliance documents be kept? Until decided: no automatic cleanup, and on a GDPR
  erasure the flight stays with the pilot shown as "Slettet bruger".
- From the brief: accounting system for invoice drafts; real values for [PRIS], [BELØB], [X] delivery days and model
  precision [XX]; who on the customer side may approve a quote (v1: anyone allowed to order).
- Customers in several organisations see the first one; the server accepts `X-Hojde-Org`, but the portal has no
  organisation switcher yet.
- Customers are not mailed about a weather hold or a moved date yet: they see it in the portal, and the webhooks
  `hojde.weather.hold` and `hojde.task.ready` are there for a notification later (P5).
- Raised in v1: is "Afventer godkendelse" Højde preparing a quote or a date (v1: yes)? Should a weather hold move the
  date automatically (v1: flag only)?
