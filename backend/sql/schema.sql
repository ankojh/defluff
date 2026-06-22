create table if not exists url_submissions (
    id bigserial primary key,
    url text not null,
    status text not null default 'pending',
    error_message text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_url_submissions_status
    on url_submissions (status);

create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_url_submissions_updated_at on url_submissions;

create trigger trg_url_submissions_updated_at
before update on url_submissions
for each row
execute function set_updated_at();

create table if not exists consumed_items (
    id bigserial primary key,
    url text not null unique,
    title text,
    kind text not null,
    source text not null,
    language text,
    text_hash text not null,
    text_excerpt text not null,
    summary text not null,
    key_points jsonb not null default '[]'::jsonb,
    highlights jsonb not null default '[]'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    consumed_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_consumed_items_url
    on consumed_items (url);

create index if not exists idx_consumed_items_consumed_at
    on consumed_items (consumed_at desc);

create index if not exists idx_consumed_items_search
    on consumed_items
    using gin (
        to_tsvector(
            'english',
            coalesce(title, '') || ' ' || summary || ' ' || text_excerpt
        )
    );

drop trigger if exists trg_consumed_items_updated_at on consumed_items;

create trigger trg_consumed_items_updated_at
before update on consumed_items
for each row
execute function set_updated_at();

-- Personal knowledge: individual chapters/highlights the user explicitly marks
-- as "learned". Used to compress already-known material in future consumption.
create table if not exists knowledge_items (
    id bigserial primary key,
    kind text not null,
    source_url text not null,
    source_title text,
    title text not null,
    summary text not null,
    detail text not null default '',
    metadata jsonb not null default '{}'::jsonb,
    learned_at timestamptz not null default now(),
    unique (source_url, kind, title)
);

create index if not exists idx_knowledge_items_learned_at
    on knowledge_items (learned_at desc);

create index if not exists idx_knowledge_items_search
    on knowledge_items
    using gin (
        to_tsvector('english', title || ' ' || summary || ' ' || detail)
    );
