select * from {{ ref('mart_forecast_accuracy') }}
where lead_weeks < 0 or lead_weeks is null
