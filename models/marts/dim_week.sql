select
    week_key,
    week_start,
    week_ending,
    fiscal_year,
    fiscal_quarter,
    fiscal_period,
    fiscal_week,
    holiday_event
from {{ ref('stg_fiscal_calendar') }}
