select
    cast(sku_id as varchar) as sku_id,
    cast(week_key as varchar) as week_key,
    cast(forecast_run_week as varchar) as forecast_run_week,
    cast(forecast_units as integer) as forecast_units,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'forecast_chain_weekly') }}
