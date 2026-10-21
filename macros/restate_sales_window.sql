{% macro restate_sales_window() %}
    {#- Runs before fct_sales loads. The window is anchored on the source's latest week, not the target's, so the
        boundary does not move as rows are deleted and a week missing from the source is still removed. -#}
    {%- if is_incremental() %}
        delete from {{ this }}
        where week_ending > (
            select max(week_ending) - {{ var('sales_restatement_lookback_days', 28) }}
            from {{ ref('int_sales_enriched') }}
        )
    {%- endif %}
{% endmacro %}
