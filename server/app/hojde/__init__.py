"""Højde: the drone-data platform's customer portal (/portal) and backoffice (/backoffice).

    rules.py      the rules the screens imply (pure functions)
    providers.py  weather and drone zones (deterministic stubs)
    access.py     who may do what: a person's Højde membership, resolved from the Gær session
    ops.py        numbering, turning an order into a task, the checklist and the weather rule
    gdpr.py       what the GDPR export and erasure do with Højde data
    seed.py       the demo tenant (python -m app.hojde.seed)
    admin.py      the first staff membership on a new instance (python -m app.hojde.admin)

Design and plan: specs/hojde-platform/. Ported from surdej-v2 modules/member-hojde (P0–P2).
"""
