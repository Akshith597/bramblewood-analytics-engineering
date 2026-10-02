select
    cast(store_id as integer) as store_id,
    cast(store_name as varchar) as store_name,
    cast(city as varchar) as city,
    cast(state as varchar) as state,
    cast(format as varchar) as format,
    cast(sqft as integer) as sqft,
    cast(price_zone as varchar) as price_zone,
    cast(pos_system as varchar) as pos_system,
    cast(open_date as date) as open_date,
    cast(remodel_start as date) as remodel_start,
    cast(remodel_end as date) as remodel_end,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'stores') }}
