select
    cast(sku_id as varchar) as sku_id,
    cast(effective_start as date) as effective_start,
    cast(effective_end as date) as effective_end,
    cast(unit_cost as decimal(18, 2)) as unit_cost,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'item_cost') }}
