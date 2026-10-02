with sequenced as (
    select
        sku_id,
        effective_start,
        effective_end,
        unit_cost,
        _source_row,
        lead(effective_start) over (
            partition by sku_id order by effective_start
        ) as next_start
    from {{ ref('stg_item_cost') }}
)

select
    sku_id,
    effective_start,
    effective_end as source_effective_end,
    case
        when next_start is not null and (effective_end is null or effective_end >= next_start)
            then next_start - 1
        else effective_end
    end as effective_end,
    next_start is not null and (effective_end is null or effective_end >= next_start) as overlap_adjusted,
    unit_cost,
    _source_row
from sequenced
