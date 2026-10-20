-- Each snapshotted key has at most one current version, and every closed version ends after it starts
-- and no later than the next version begins.
with versions as (
    select
        'snap_items' as snapshot_name,
        sku_id as entity_id,
        dbt_valid_from,
        dbt_valid_to
    from {{ ref('snap_items') }}
    union all
    select
        'snap_stores' as snapshot_name,
        cast(store_id as varchar) as entity_id,
        dbt_valid_from,
        dbt_valid_to
    from {{ ref('snap_stores') }}
),

sequenced as (
    select
        *,
        lead(dbt_valid_from) over (
            partition by snapshot_name, entity_id order by dbt_valid_from
        ) as next_valid_from
    from versions
)

select
    snapshot_name,
    entity_id,
    'multiple current versions' as failure
from versions
where dbt_valid_to is null
group by snapshot_name, entity_id
having count(*) > 1
union all
select
    snapshot_name,
    entity_id,
    'invalid validity window' as failure
from sequenced
where
    dbt_valid_to <= dbt_valid_from
    or (next_valid_from is not null and (dbt_valid_to is null or dbt_valid_to > next_valid_from))
