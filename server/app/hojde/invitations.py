"""Invitation e-mails for Højde customer users.

An invitation is a hojde_members row with status "inviteret" and the e-mail it was sent to. The mail goes out as the
job hojde.invitation.mail (enqueued in the same transaction as the invitation, so it is retried and visible in
/admin/jobs). The person signs in to Gær with that e-mail and a code; the membership is linked at that first login
(app/hojde/access.py) if the invitation is younger than 7 days.
"""

import html

from app import config, db, jobs, mail, settings_store
from app.hojde import rules


async def enqueue(conn, member_id: int) -> None:
    await jobs.enqueue(conn, "hojde.invitation.mail", {"member_id": member_id},
                       dedupe_key=f"hojde.invitation.mail:{member_id}")


def invitation_mail(*, org_name: str, inviter: str | None, email: str, expires: str, link: str,
                    app_name: str) -> tuple[str, str, str]:
    who = f"{inviter} har" if inviter else "Du er blevet"
    subject = f"Invitation til {org_name} på Højde"
    lead = (f"{who} inviteret dig til {org_name} på Højde, hvor I følger jeres bygninger og bestiller droneflyvninger."
            if inviter else
            f"Du er inviteret til {org_name} på Højde, hvor I følger jeres bygninger og bestiller droneflyvninger.")
    how = f"Log ind med din e-mail {email} og den kode, du får tilsendt. Invitationen gælder til {expires}."
    text = f"{lead}\n\n{how}\n\n{link}\n"
    e = html.escape
    body = (f"<p>{e(lead)}</p><p>{e(how)}</p>"
            f'<p><a href="{e(link)}">Log ind på {e(app_name)}</a></p>'
            f'<p style="color:#64748b;font-size:13px">Kender du ikke afsenderen, kan du se bort fra denne mail.</p>')
    return subject, text, body


@jobs.handler("hojde.invitation.mail")
async def send_invitation(payload: dict, job: dict) -> dict:
    """Skipped when the invitation is gone or no longer waiting. A mail error raises, so the job is retried."""
    async with db.connection() as conn:
        row = await db.fetch_one(conn, """
            select m.email, m.status, m.invitation_sent_at, o.name as org_name, i.name as inviter
            from hojde_members m join hojde_organizations o on o.id = m.org_id
            left join hojde_members i on i.id = m.invited_by and i.anonymised_at is null
            where m.id = %s""", (payload["member_id"],))
        if row is None or row["status"] != "inviteret" or row["invitation_sent_at"] is None:
            return {"skipped": "not invited"}
        app_name = await settings_store.get(conn, "app_name")
    expires = rules.invitation_expires_at(row["invitation_sent_at"]).astimezone(rules.TIME_ZONE).strftime("%d.%m.%Y")
    subject, text, body = invitation_mail(org_name=row["org_name"], inviter=row["inviter"], email=row["email"],
                                          expires=expires, link=config.settings.origin.rstrip("/") + "/login",
                                          app_name=app_name)
    await mail.send_mail(row["email"], subject, text, body, app_name)
    return {"sent": True}
