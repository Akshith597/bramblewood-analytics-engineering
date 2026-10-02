select
    md5(concat_ws('|', s.store_id, s.sku_id, s.week_key)) as sales_key,
    s.*,
    c.unit_cost,
    r.reg_retail as regular_unit_price,
    cast(s.units * c.unit_cost as decimal(18, 2)) as estimated_cogs,
    cast(s.net_sales - s.units * c.unit_cost as decimal(18, 2)) as gross_profit_before_funding
from {{ ref('int_sales_keys') }} as s
left join {{ ref('int_item_cost_intervals') }} as c
    on
        s.sku_id = c.sku_id
        and s.week_ending >= c.effective_start
        and (c.effective_end is null or s.week_ending <= c.effective_end)
left join {{ ref('stg_reg_price') }} as r
    on
        s.sku_id = r.sku_id
        and s.price_zone = r.price_zone
        and s.week_ending >= r.effective_start
        and (r.effective_end is null or s.week_ending <= r.effective_end)
