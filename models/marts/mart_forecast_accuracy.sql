with actuals as (
    select
        sku_id,
        week_key,
        cast(sum(units) as bigint) as actual_units,
        count(distinct store_id) as reporting_stores
    from {{ ref('fct_sales') }}
    group by 1, 2
)

select
    f.sku_id,
    f.week_key,
    f.forecast_run_week,
    f.forecast_units,
    a.actual_units,
    a.reporting_stores,
    a.week_key is not null as has_actual,
    f.forecast_units - a.actual_units as error_units,
    abs(f.forecast_units - a.actual_units) as absolute_error_units,
    {{ dbt.datediff('r.week_start', 'w.week_start', 'day') }}
    / 7 as lead_weeks
from {{ ref('stg_forecast') }} as f
left join actuals as a on f.sku_id = a.sku_id and f.week_key = a.week_key
left join {{ ref('dim_week') }} as w on f.week_key = w.week_key
left join {{ ref('dim_week') }} as r on f.forecast_run_week = r.week_key
