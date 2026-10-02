select * from {{ ref('int_item_cost_intervals') }}
where effective_end < effective_start or unit_cost < 0 or unit_cost is null
