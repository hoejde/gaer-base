"""The first Højde staff membership on a new instance — there is no automatic Højde administrator.

    python -m app.hojde.admin add-staff emil@hojde.dk --name Emil --roles administrator,pilot

Creates a staff membership for the e-mail (or reactivates and updates one). It is linked to the Gær user the first
time that person signs in. Audited (actor: none, via: cli). Later staff are managed in the backoffice.
"""

import argparse
import asyncio
import re
import sys

from app import db
from app.hojde import rules
from app.logs import RequestMeta, audit

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,253}$")


async def add_staff(conn, email: str, name: str, roles: list[str], *, meta: RequestMeta | None = None) -> dict:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Ugyldig e-mailadresse")
    if not roles or any(r not in rules.STAFF_ROLES for r in roles):
        raise ValueError(f"Roller skal være blandt: {', '.join(rules.STAFF_ROLES)}")
    meta = meta or RequestMeta()
    before = await db.fetch_one(conn, "select id, name, roles, status from hojde_members "
                                      "where kind = 'staff' and email = %s for update", (email,))
    if before is None:
        row = await db.fetch_one(conn, """insert into hojde_members (email, name, kind, roles) values (%s, %s, 'staff', %s)
                                          returning id, name, roles, status""", (email, name, roles))
        await audit(conn, "create", actor_id=None, meta=meta, table="hojde_members", row_id=row["id"],
                    after={"kind": "staff", "roles": roles}, via="cli")
    else:
        row = await db.fetch_one(conn, """update hojde_members set name = %s, roles = %s, status = 'aktiv'
                                          where id = %s returning id, name, roles, status""",
                                 (name, roles, before["id"]))
        await audit(conn, "update", actor_id=None, meta=meta, table="hojde_members", row_id=row["id"],
                    before={"roles": before["roles"], "status": before["status"]},
                    after={"roles": roles, "status": "aktiv"}, via="cli")
    return row


async def _main(args) -> int:
    await db.open_pools()
    try:
        async with db.connection() as conn:
            row = await add_staff(conn, args.email, args.name, [r.strip() for r in args.roles.split(",") if r.strip()])
    except ValueError as e:
        print(f"Fejl: {e}")
        return 1
    finally:
        await db.close_pools()
    print(f"Medarbejder #{row['id']} {row['name']} ({', '.join(row['roles'])}) er klar. "
          "Kobles til brugeren ved første login.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add-staff", help="opret eller genaktivér en medarbejder")
    add.add_argument("email")
    add.add_argument("--name", required=True)
    add.add_argument("--roles", default="administrator", help="kommasepareret, fx administrator,pilot")
    return asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
