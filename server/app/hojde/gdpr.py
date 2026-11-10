"""Højde in the GDPR export and erasure (called from app/gdpr.py).

Personal data in Højde is the person's memberships (name, e-mail, roles, certificates) and what is linked to them:
orders they created, quotes they approved, flights they flew, checklist items they ticked, findings they approved and
pilot certificates they hold. Names are never copied into those tables, so anonymising the membership removes the
person everywhere while flights and tasks keep their reference: the logbook stays complete and shows
"Slettet bruger". How long the logbook itself is kept is not decided yet (no retention policy).

Site contacts typed on locations and orders (vicevært, byggeleder) belong to the customer's organisation and are not
tied to a Gær user; they are removed with the organisation.
"""

from app import db

DELETED_NAME = "Slettet bruger"


async def _member_ids(conn, user_id: int, email: str | None) -> list[int]:
    rows = await db.fetch_all(conn, """select id from hojde_members
                                       where user_id = %s or (user_id is null and email = %s and anonymised_at is null)""",
                              (user_id, (email or "").lower()))
    return [r["id"] for r in rows]


async def export(conn, user_id: int, email: str | None) -> dict:
    ids = await _member_ids(conn, user_id, email)

    async def rows(sql):
        return await db.fetch_all(conn, sql, (ids,))

    return {
        "memberships": await rows("""
            select m.id, m.kind, o.name as organisation, m.name, m.email, m.roles, m.location_scope, m.may_order,
                   m.status, m.certificates, m.invitation_sent_at, m.created_at, m.last_seen_at
            from hojde_members m left join hojde_organizations o on o.id = m.org_id
            where m.id = any(%s) order by m.created_at"""),
        "orders_created": await rows("""select number, status, created_at from hojde_orders
                                        where created_by = any(%s) order by created_at"""),
        "quotes_approved": await rows("""select number, quote_approved_at from hojde_orders
                                         where quote_approved_by = any(%s) order by quote_approved_at"""),
        "flights_as_pilot": await rows("""select number, started_at, sorties, minutes_per_sortie, wind_ms, incident
                                          from hojde_flights where pilot_id = any(%s) order by started_at"""),
        "tasks_as_pilot": await rows("""select number, scheduled_at, status from hojde_tasks
                                        where pilot_id = any(%s) order by scheduled_at"""),
        "checklist_items_done": await rows("""select t.number as task, c.label, c.done_at
                                              from hojde_checklist_items c join hojde_tasks t on t.id = c.task_id
                                              where c.done_by = any(%s) order by c.done_at"""),
        "findings_approved": await rows("""select location_id, visit_date, number, title, qc_state from hojde_findings
                                           where approved_by = any(%s) order by visit_date, number"""),
        "certificates": await rows("""select kind, title, reference, expires_at from hojde_compliance_documents
                                      where holder_id = any(%s) order by expires_at"""),
    }


async def erase(conn, user_id: int, email: str | None) -> int:
    """Anonymises the user's memberships, and invitations to their e-mail not yet claimed. Returns how many."""
    ids = await _member_ids(conn, user_id, email)
    if ids:
        await conn.execute("""update hojde_members
                              set name = %s, email = 'slettet-' || id || '@slettet.invalid', user_id = null,
                                  status = 'deaktiveret', certificates = '', location_ids = '{}', may_order = false,
                                  last_seen_at = null, anonymised_at = now()
                              where id = any(%s)""", (DELETED_NAME, ids))
        await conn.execute("""update hojde_compliance_documents set reference = '' where holder_id = any(%s)""", (ids,))
    return len(ids)
