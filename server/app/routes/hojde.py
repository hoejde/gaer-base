"""Højde API (/api/hojde): the customer portal and the backoffice. Who may do what: app/hojde/access.py.

    GET /api/hojde/me     the signed-in person's Højde memberships, where the app should land them (/portal or
                          /backoffice) and whether a second factor is needed. Links waiting memberships (invitations)
                          to the user on first sight.

The portal (/api/hojde/portal/…) and backoffice (/api/hojde/backoffice/…) endpoints follow in phases 2 and 3
(specs/hojde-platform/PLAN.md).
"""

from fastapi import APIRouter, Depends

from app.hojde.access import HojdeContext, hojde_context

router = APIRouter(prefix="/api/hojde", tags=["hojde"])


@router.get("/me")
async def me(ctx: HojdeContext = Depends(hojde_context)):
    return {
        "staff": ctx.staff.public() if ctx.staff else None,
        "customer": ctx.customer.public() if ctx.customer else None,
        "customers": [{"org_id": c.org_id, "org_name": c.org_name} for c in ctx.customers],
        "landing": ctx.landing,
        "mfa": {"required": ctx.mfa_required, "has_factor": ctx.has_factor, "proven": ctx.mfa_proven},
    }
