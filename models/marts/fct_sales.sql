{{
    config(
        materialized='incremental',
        incremental_strategy='delete+insert',
        unique_key='week_key',
        on_schema_change='fail'
    )
}}

-- Incremental runs restate whole fiscal weeks inside the lookback window: delete+insert on week_key
-- removes rows that disappeared from a corrected extract as well as replacing changed ones. Corrections
-- older than the window need `dbt build --full-refresh`; verify_repeatability.py proves the incremental
-- path reproduces a full build.
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
        select max(week_ending) - {{ var('sales_restatement_lookback_days', 28) }}
        from {{ this }}
    )
{% endif %}
