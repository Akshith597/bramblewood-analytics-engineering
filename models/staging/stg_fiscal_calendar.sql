select
    cast(week_key as varchar) as week_key,
    cast(week_start as date) as week_start,
    cast(week_ending as date) as week_ending,
    cast(fiscal_year as integer) as fiscal_year,
    cast(fiscal_quarter as integer) as fiscal_quarter,
    cast(fiscal_period as integer) as fiscal_period,
    cast(fiscal_week as integer) as fiscal_week,
    cast(holiday_event as varchar) as holiday_event,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'fiscal_calendar') }}
