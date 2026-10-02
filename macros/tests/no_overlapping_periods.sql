{% test no_overlapping_periods(model, partition_by, start_col='effective_start', end_col='effective_end') %}
with periods as (
    select
        *,
        row_number() over (
            order by
                {% for column in partition_by %}{{ column }},{% endfor %}
                {{ start_col }}, {{ end_col }}
        ) as period_row_id
    from {{ model }}
)
select
    a.*
from periods as a
inner join periods as b
    on a.period_row_id < b.period_row_id
    {% for column in partition_by %}
    and a.{{ column }} is not distinct from b.{{ column }}
    {% endfor %}
    and a.{{ start_col }} <= coalesce(b.{{ end_col }}, date '9999-12-31')
    and b.{{ start_col }} <= coalesce(a.{{ end_col }}, date '9999-12-31')
{% endtest %}
