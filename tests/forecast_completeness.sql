{{ config(severity='warn') }}
-- A forecast row without a quantity cannot be scored. It is excluded from WAPE and bias (see is_scored_pair) and
-- counted in evidence/forecast_metrics.csv; this warning makes the gap visible in every build.
select
    sku_id,
    week_key,
    forecast_run_week
from {{ ref('mart_forecast_accuracy') }}
where forecast_units is null
