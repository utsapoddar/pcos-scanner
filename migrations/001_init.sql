create table if not exists profile (
    id integer primary key check (id = 1),
    pcos_type text not null,
    insulin_resistance boolean not null,
    irregular_periods boolean not null,
    acne_or_hair boolean not null,
    inflammation_bloating boolean not null,
    cravings boolean not null,
    weight_loss_goal boolean not null,
    dietary_prefs text not null default ''
);

create table if not exists saved_foods (
    barcode text primary key,
    product_name text,
    score real not null,
    verdict text not null,
    scanned_at bigint not null,
    list_type text not null check (list_type in ('safe', 'sometimes', 'avoid'))
);

create table if not exists personalization_cache (
    barcode text not null,
    profile_hash text not null,
    payload jsonb not null,
    primary key (barcode, profile_hash)
);
