"""Who may do what in Højde.

A person signs in to Gær as usual (e-mail + code, passkey). Their Højde access is a membership (hojde_members):

- The first time a signed-in user is seen, memberships with their e-mail and no user yet are linked to them, and an
  invitation becomes active — unless it is older than 7 days (then it has to be sent again). Gær has verified the
  e-mail with a code, so the address is theirs. Each link is audited.
- A staff membership opens /backoffice. Some actions need a role (staff_of(ctx, "pilot")); administrators pass all.
- A customer membership opens /portal, scoped to its organisation. Someone in several organisations picks one with
  the X-Hojde-Org header; only their own memberships can be picked.
- Staff always need a second factor in the session, and so do members of an organisation with require_2fa: without
  any factor the answer is mfa_setup_required, with one that was not used in this session stepup_required — the same
  403 codes the rest of Gær uses.

There is no automatic Højde administrator: a new instance gets its first staff membership with
`python -m app.hojde.admin add-staff` (app/hojde/admin.py), audited.
"""

from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, Request

from app import db, mfa
from app.hojde import rules
from app.logs import audit
from app.sessions import Principal, current_user


@dataclass(frozen=True)
class Membership:
    id: int
    kind: str                       # customer | staff
    org_id: int | None
    org_name: str | None
    require_2fa: bool
    name: str
    email: str
    roles: tuple[str, ...]
    location_scope: str
    location_ids: tuple[int, ...]
    may_order: bool

    def has_role(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)

    def public(self) -> dict:
        out = {"id": self.id, "kind": self.kind, "name": self.name, "email": self.email, "roles": list(self.roles),
               "role_labels": [rules.ROLE_LABEL[r] for r in self.roles]}
        if self.kind == "customer":
            out.update(org_id=self.org_id, org_name=self.org_name, require_2fa=self.require_2fa,
                       location_scope=self.location_scope, location_ids=list(self.location_ids),
                       may_order=self.may_order, can_order=rules.can_order(self.roles, self.may_order),
                       can_manage_organization=rules.can_manage_organization(self.roles))
        return out


@dataclass
class HojdeContext:
    principal: Principal
    staff: Membership | None
    customers: list[Membership] = field(default_factory=list)
    customer: Membership | None = None   # the organisation this request acts in
    has_factor: bool = False             # the user has a confirmed passkey, security key or authenticator app

    @property
    def mfa_required(self) -> bool:
        return self.staff is not None or (self.customer is not None and self.customer.require_2fa)

    @property
    def mfa_proven(self) -> bool:
        return self.principal.mfa_at is not None

    @property
    def landing(self) -> str | None:
        """Where the app on / sends the person: staff to the backoffice, customers to the portal."""
        return "/backoffice" if self.staff else "/portal" if self.customer else None


MEMBERSHIP_SQL = """
    select m.id, m.kind, m.org_id, o.name as org_name, coalesce(o.require_2fa, false) as require_2fa, m.name, m.email,
           m.roles, m.location_scope, m.location_ids, m.may_order
    from hojde_members m left join hojde_organizations o on o.id = m.org_id
    where m.user_id = %s and m.status = 'aktiv'
    order by m.created_at, m.id"""


def _membership(row: dict) -> Membership:
    return Membership(id=row["id"], kind=row["kind"], org_id=row["org_id"], org_name=row["org_name"],
                      require_2fa=row["require_2fa"], name=row["name"], email=row["email"], roles=tuple(row["roles"]),
                      location_scope=row["location_scope"], location_ids=tuple(row["location_ids"]),
                      may_order=row["may_order"])


async def link_memberships(conn, principal: Principal) -> list[int]:
    """Links memberships waiting for this user's e-mail; returns their ids. Audited per membership."""
    if not principal.email:
        return []
    linked = await db.fetch_all(conn, """
        with waiting as (
            select id, status from hojde_members
            where user_id is null and email = %(email)s and anonymised_at is null
              and (status = 'aktiv'
                   or (status = 'inviteret' and invitation_sent_at >= now() - make_interval(days => %(days)s)))
            for update)
        update hojde_members m set user_id = %(user)s, status = 'aktiv', last_seen_at = now()
        from waiting w where m.id = w.id
        returning m.id, w.status as old_status""",
        {"email": principal.email.lower(), "user": principal.user_id, "days": rules.INVITATION_DAYS})
    for row in linked:
        await audit(conn, "update", actor_id=principal.user_id, meta=principal.meta, table="hojde_members",
                    row_id=row["id"], before={"user_id": None, "status": row["old_status"]},
                    after={"user_id": principal.user_id, "status": "aktiv"}, via="first_login")
    return [r["id"] for r in linked]


async def load(conn, principal: Principal, wanted_org: int | None = None) -> HojdeContext:
    await link_memberships(conn, principal)
    members = [_membership(r) for r in await db.fetch_all(conn, MEMBERSHIP_SQL, (principal.user_id,))]
    staff = next((m for m in members if m.kind == "staff"), None)
    customers = [m for m in members if m.kind == "customer"]
    customer = next((m for m in customers if m.org_id == wanted_org), customers[0] if customers else None)
    has_factor = (await mfa.factors(conn, principal.user_id))["total"] > 0 if members else False
    return HojdeContext(principal=principal, staff=staff, customers=customers, customer=customer,
                        has_factor=has_factor)


async def hojde_context(request: Request, principal: Principal = Depends(current_user)) -> HojdeContext:
    header = request.headers.get("x-hojde-org", "")
    async with db.connection() as conn:
        return await load(conn, principal, int(header) if header.isdigit() else None)


# ── Guards ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def require_second_factor(ctx: HojdeContext) -> None:
    if not ctx.mfa_required:
        return
    if not ctx.has_factor:
        raise mfa.mfa_error("mfa_setup_required",
                            "Højde kræver en passkey, sikkerhedsnøgle eller godkendelsesapp. Tilføj en under Konto.")
    if not ctx.mfa_proven:
        raise mfa.mfa_error("stepup_required", "Bekræft med din passkey, sikkerhedsnøgle eller godkendelsesapp først")


def customer_of(ctx: HojdeContext) -> Membership:
    """The customer membership behind a /portal request."""
    if ctx.customer is None:
        raise HTTPException(403, "Du er ikke tilknyttet en kundeorganisation")
    require_second_factor(ctx)
    return ctx.customer


def customer_admin_of(ctx: HojdeContext) -> Membership:
    member = customer_of(ctx)
    if not rules.can_manage_organization(member.roles):
        raise HTTPException(403, "Kun for kundeadministratorer")
    return member


def staff_of(ctx: HojdeContext, *any_of: str) -> Membership:
    """The staff membership behind a /backoffice request; with roles, one of them (administrators pass all)."""
    if ctx.staff is None:
        raise HTTPException(403, "Kun for Højdes medarbejdere")
    if any_of and not ctx.staff.has_role("administrator", *any_of):
        names = [rules.ROLE_LABEL[r].lower() for r in any_of]
        either = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} eller {names[-1]}"
        raise HTTPException(403, f"Kræver rollen {either}")
    require_second_factor(ctx)
    return ctx.staff


async def require_customer(ctx: HojdeContext = Depends(hojde_context)) -> HojdeContext:
    customer_of(ctx)
    return ctx


def require_staff(*any_of: str):
    async def dependency(ctx: HojdeContext = Depends(hojde_context)) -> HojdeContext:
        staff_of(ctx, *any_of)
        return ctx
    return dependency
