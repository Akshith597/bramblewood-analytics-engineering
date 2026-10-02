{% macro normalize_upc(column_name) -%}
    lpad(trim(cast({{ column_name }} as varchar)), 12, '0')
{%- endmacro %}
