select
    cast(store_id as integer) as store_id,
    cast(planogram_id as varchar) as planogram_id,
    cast(effective_start as date) as effective_start,
    cast(effective_end as date) as effective_end,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'store_planogram') }}
