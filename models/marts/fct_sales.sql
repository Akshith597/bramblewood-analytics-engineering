{{
    config(
        materialized='incremental',
        incremental_strategy='append',
        on_schema_change='fail',
        pre_hook="{{ restate_sales_window() }}"
    )
}}

-- Incremental runs restate a date window, not just the week keys present in the new data. The pre-hook deletes
-- every week ending within the lookback of the latest source week, including weeks that vanished from a corrected
-- extract; the select then loads every source row newer than what remains, which is everything when the target is
-- empty. Corrections older than the window need `dbt build --full-refresh`. scripts/verify_incremental.py tests
-- these cases; scripts/verify_repeatability.py separately shows an unchanged input rebuilds identically.
select
    sales_key,
    store_id,
    upc,
    week_ending,
    units,
    gross_sales,
    promo_discount,
    net_sales,
    _source_file,
    _source_row,
    sku_id,
    week_key,
    fiscal_year,
    price_zone,
    store_key_matched,
    store_open,
    remodel_week,
    unit_cost,
    regular_unit_price,
    estimated_cogs,
    gross_profit_before_funding
from {{ ref('int_sales_enriched') }}
{% if is_incremental() %}
    where week_ending > (
        select coalesce(max(week_ending), date '1900-01-01')
        from {{ this }}
    )
{% endif %}
