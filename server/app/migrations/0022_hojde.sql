-- Højde: the drone-data platform's customer portal (/portal) and backoffice (/backoffice). Ported from the surdej-v2
-- module member-hojde (phases P0–P2); the design and plan are in specs/hojde-platform/.
--
-- hojde_organizations        a customer organisation (a housing association, a contractor, …).
-- hojde_members              a person's Højde access: a customer membership (org_id set) or a staff membership (org_id
--                            null). Linked to users by e-mail at first login. Personal data: in the GDPR export, and
--                            anonymised on erasure (the row stays, so flights and tasks keep their pilot reference).
-- hojde_locations            buildings, construction sites and areas a customer follows. contact_* is the site contact.
-- hojde_services             the service catalogue a customer orders from.
-- hojde_orders               an order (B-1042). Status flow in app/hojde/rules.py.
-- hojde_equipment            drones, batteries and other equipment.
-- hojde_tasks                a planned visit (OP-2026-0418): one per flight day of an order.
-- hojde_checklist_items      the pre-flight checklist of a task; "Markér klar" needs all of them.
-- hojde_flights              the logbook (FL-0931). No retention policy: how long it is kept is not decided yet.
-- hojde_compliance_documents operator registration, insurance and pilot certificates with their expiry.
-- hojde_findings             AI findings per location and visit; customers see only approved ones.
--
-- Names of people are never copied into other tables: they are looked up through hojde_members, so anonymising a
-- member removes the name everywhere.

create table hojde_organizations (
    id               bigserial primary key,
    name             text not null check (length(name) between 1 and 200),
    cvr              text check (cvr ~ '^[0-9]{8}$'),
    billing_address  text check (length(billing_address) <= 300),
    ean              text check (ean ~ '^[0-9]{13}$'),
    require_2fa      boolean not null default false,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);

create table hojde_members (
    id                  bigserial primary key,
    user_id             bigint references users (id) on delete set null,
    email               text not null check (email = lower(email) and length(email) between 3 and 320),
    name                text not null check (length(name) between 1 and 200),
    kind                text not null check (kind in ('customer', 'staff')),
    org_id              bigint references hojde_organizations (id) on delete cascade,
    roles               text[] not null check (cardinality(roles) between 1 and 4),
    location_scope      text not null default 'alle' check (location_scope in ('alle', 'udvalgte')),
    location_ids        bigint[] not null default '{}',
    may_order           boolean not null default false,
    status              text not null default 'aktiv' check (status in ('aktiv', 'inviteret', 'deaktiveret')),
    certificates        text not null default '' check (length(certificates) <= 200),
    invited_by          bigint references hojde_members (id) on delete set null,
    invitation_sent_at  timestamptz,
    last_seen_at        timestamptz,
    anonymised_at       timestamptz,
    created_at          timestamptz not null default now(),
    check ((kind = 'customer') = (org_id is not null)),
    check (kind <> 'customer' or roles <@ array['kundeadministrator', 'kundebruger']),
    check (kind <> 'staff' or roles <@ array['administrator', 'analytiker', 'pilot', 'kundeansvarlig'])
);
create unique index hojde_members_customer_email on hojde_members (org_id, email) where kind = 'customer';
create unique index hojde_members_staff_email on hojde_members (email) where kind = 'staff';
create index hojde_members_user on hojde_members (user_id) where user_id is not null;
create index hojde_members_unlinked on hojde_members (email) where user_id is null;

create table hojde_locations (
    id               bigserial primary key,
    org_id           bigint not null references hojde_organizations (id) on delete cascade,
    name             text not null check (length(name) between 1 and 200),
    type             text not null check (type in ('bygning', 'byggeplads', 'omraade')),
    address          text not null check (length(address) between 1 and 300),
    lat              double precision check (lat between -90 and 90),
    lng              double precision check (lng between -180 and 180),
    contact_name     text not null default '' check (length(contact_name) <= 200),
    contact_phone    text not null default '' check (length(contact_phone) <= 40),
    access_notes     text not null default '' check (length(access_notes) <= 2000),
    restricted_zone  boolean not null default false,
    created_at       timestamptz not null default now()
);
create index hojde_locations_org on hojde_locations (org_id);

create table hojde_services (
    id              bigserial primary key,
    key             text not null unique check (key ~ '^[a-z0-9-]{1,60}$'),
    line            text not null check (line in ('drone', 'data', 'ai')),
    title           text not null check (length(title) between 1 and 200),
    short_label     text not null check (length(short_label) between 1 and 60),
    description     text not null default '',
    specs           text[] not null default '{}',
    price_from_ore  integer check (price_from_ore >= 0),   -- null: the screens' [PRIS] placeholder
    price_unit      text not null default 'pr. besøg',
    industry        text not null default '',
    equipment       text not null default '',
    permit_class    text not null check (permit_class in ('A1', 'A2', 'A3', 'BVLOS')),
    needs_quote     boolean not null default false,
    active          boolean not null default true,
    sort            integer not null default 0
);

create table hojde_orders (
    id                   bigserial primary key,
    number               text not null unique check (number ~ '^B-[0-9]{4,}$'),
    org_id               bigint not null references hojde_organizations (id) on delete cascade,
    location_id          bigint not null references hojde_locations (id),
    service_id           bigint not null references hojde_services (id),
    status               text not null check (status in ('afventer_godkendelse', 'tilbud_sendt', 'godkendt', 'planlagt',
                                                         'vejrforbehold', 'leveret', 'aflyst')),
    frequency            text not null default 'enkelt' check (frequency in ('enkelt', 'abonnement')),
    visits               integer check (visits between 1 and 365),
    preferred_from       date,
    preferred_to         date,
    time_of_day          text not null default 'hele_dagen' check (time_of_day in ('hele_dagen', 'formiddag', 'eftermiddag')),
    scheduled_at         timestamptz,
    contact_name         text not null default '' check (length(contact_name) <= 200),
    contact_phone        text not null default '' check (length(contact_phone) <= 40),
    access_notes         text not null default '' check (length(access_notes) <= 2000),
    subject              text not null default '' check (length(subject) <= 200),   -- what to look at: "tag og facade"
    notes                text not null default '' check (length(notes) <= 4000),
    report_recipient     text not null default '' check (length(report_recipient) <= 200),
    quote_ore            integer check (quote_ore >= 0),
    quote_sent_at        timestamptz,
    quote_approved_at    timestamptz,
    quote_approved_by    bigint references hojde_members (id) on delete set null,
    access_confirmed_at  timestamptz,
    delivered_at         timestamptz,
    cancelled_at         timestamptz,
    created_by           bigint references hojde_members (id) on delete set null,
    created_at           timestamptz not null default now(),
    check (frequency = 'enkelt' or visits is not null),
    check (preferred_to is null or preferred_from is null or preferred_to >= preferred_from)
);
create index hojde_orders_org_status on hojde_orders (org_id, status);

create table hojde_equipment (
    id             bigserial primary key,
    name           text not null check (length(name) between 1 and 100),
    kind           text not null check (kind in ('drone', 'batteri', 'andet')),
    model          text not null default '',
    serial         text not null default '',
    c_class        text check (c_class in ('C0', 'C1', 'C2', 'C3', 'C4')),
    usage_minutes  integer not null default 0 check (usage_minutes >= 0),
    cycles         integer check (cycles >= 0),
    next_service   text not null default '',
    status         text not null default 'klar' check (status in ('klar', 'til_kontrol', 'til_service')),
    sort           integer not null default 0,
    created_at     timestamptz not null default now()
);

create table hojde_tasks (
    id                    bigserial primary key,
    number                text not null unique check (number ~ '^OP-[0-9]{4}-[0-9]{4,}$'),
    order_id              bigint not null references hojde_orders (id) on delete cascade,
    location_id           bigint not null references hojde_locations (id),
    scheduled_at          timestamptz not null,
    status                text not null default 'forberedelse'
                              check (status in ('forberedelse', 'klar', 'vejrforbehold', 'floejet', 'leveret')),
    phase                 text not null default 'forberedelse' check (phase in ('forberedelse', 'flyvning', 'data', 'leverance')),
    visit_number          integer check (visit_number >= 1),
    pilot_id              bigint references hojde_members (id) on delete set null,
    drone_id              bigint references hojde_equipment (id) on delete set null,
    permit_registered_at  timestamptz,
    ready_at              timestamptz,
    ready_by              bigint references hojde_members (id) on delete set null,
    created_at            timestamptz not null default now()
);
create index hojde_tasks_scheduled on hojde_tasks (scheduled_at);
create index hojde_tasks_order on hojde_tasks (order_id);

create table hojde_checklist_items (
    id       bigserial primary key,
    task_id  bigint not null references hojde_tasks (id) on delete cascade,
    key      text not null check (key ~ '^[a-z_]{1,40}$'),
    label    text not null,
    short    text not null,
    sort     integer not null,
    done_at  timestamptz,
    done_by  bigint references hojde_members (id) on delete set null,   -- null while done_at is set: the customer confirmed
    unique (task_id, key)
);

create table hojde_flights (
    id                  bigserial primary key,
    number              text not null unique check (number ~ '^FL-[0-9]{4,}$'),
    task_id             bigint references hojde_tasks (id) on delete set null,
    location_id         bigint not null references hojde_locations (id),
    pilot_id            bigint not null references hojde_members (id),
    drone_id            bigint not null references hojde_equipment (id),
    battery_ids         bigint[] not null default '{}',
    started_at          timestamptz not null,
    sorties             integer not null check (sorties between 1 and 100),
    minutes_per_sortie  integer not null check (minutes_per_sortie between 1 and 240),
    wind_ms             numeric(4, 1) not null check (wind_ms >= 0),
    incident            text check (length(incident) <= 2000),
    created_at          timestamptz not null default now()
);
create index hojde_flights_started on hojde_flights (started_at);
create index hojde_flights_pilot on hojde_flights (pilot_id);

create table hojde_compliance_documents (
    id          bigserial primary key,
    kind        text not null check (kind in ('operatoerregistrering', 'forsikring', 'pilotcertifikat')),
    title       text not null check (length(title) between 1 and 200),
    reference   text not null default '',
    holder_id   bigint references hojde_members (id) on delete set null,   -- the pilot of a pilot certificate
    expires_at  timestamptz,
    created_at  timestamptz not null default now(),
    check (holder_id is null or kind = 'pilotcertifikat')
);

create table hojde_findings (
    id             bigserial primary key,
    location_id    bigint not null references hojde_locations (id) on delete cascade,
    visit_date     timestamptz not null,
    order_number   text,
    number         integer not null check (number >= 1),
    title          text not null check (length(title) between 1 and 300),
    note           text not null default '',
    severity       text not null check (severity in ('kritisk', 'moderat', 'lav')),
    confidence     real check (confidence between 0 and 1),
    model_version  text,
    qc_state       text not null default 'afventer' check (qc_state in ('afventer', 'godkendt', 'rettet', 'afvist')),
    approved_by    bigint references hojde_members (id) on delete set null,
    status         text not null default 'ny' check (status in ('ny', 'planlagt', 'udbedret', 'afvist')),
    owner          text check (length(owner) <= 200),
    change         text check (change in ('ny', 'uaendret', 'forvaerret')),
    resolved_at    timestamptz,
    created_at     timestamptz not null default now()
);
create index hojde_findings_location on hojde_findings (location_id, visit_date);
