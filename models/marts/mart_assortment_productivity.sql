select
    p.store_id,
    p.sku_id,
    p.week_key,
    p.facings,
    p.planogram_id,
    p.test_planogram,
    s.sales_key is not null as has_sales_record,
    s.net_sales,
    s.units,
    s.gross_profit_before_funding,
    s.net_sales / nullif(p.facings, 0) as sales_per_scheduled_facing
from {{ ref('int_planogram_schedule') }} as p
left join {{ ref('fct_sales') }} as s
    on
        p.store_id = s.store_id
        and p.sku_id = s.sku_id
        and p.week_key = s.week_key
