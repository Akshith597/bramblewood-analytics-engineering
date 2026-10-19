{#- Adapter-dispatched helpers for the few DuckDB-specific expressions the models need. default__ is the DuckDB
    implementation the project is built and tested on; snowflake__ is written for the optional Snowflake target and
    has not been run against a live account. -#}

{% macro try_parse_date(expression, strftime_format) -%}
    {{ return(adapter.dispatch('try_parse_date')(expression, strftime_format)) }}
{%- endmacro %}

{% macro default__try_parse_date(expression, strftime_format) -%}
    cast(try_strptime({{ expression }}, '{{ strftime_format }}') as date)
{%- endmacro %}

{% macro snowflake__try_parse_date(expression, strftime_format) -%}
    try_to_date({{ expression }}, '{{ strftime_format | replace("%Y", "YYYY") | replace("%m", "MM") | replace("%d", "DD") }}')
{%- endmacro %}

{% macro regex_full_match(expression, pattern) -%}
    {{ return(adapter.dispatch('regex_full_match')(expression, pattern)) }}
{%- endmacro %}

{% macro default__regex_full_match(expression, pattern) -%}
    regexp_full_match({{ expression }}, '{{ pattern }}')
{%- endmacro %}

{#- Snowflake's regexp_like is anchored to the whole string. -#}
{% macro snowflake__regex_full_match(expression, pattern) -%}
    regexp_like({{ expression }}, '{{ pattern }}')
{%- endmacro %}
