select
    cast(sku_id as varchar) as sku_id,
    cast(price_zone as varchar) as price_zone,
    cast(effective_start as date) as effective_start,
    cast(effective_end as date) as effective_end,
    cast(reg_retail as decimal(18, 2)) as reg_retail,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'reg_price') }}
