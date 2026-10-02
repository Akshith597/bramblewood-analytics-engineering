select
    s.week_key,
    w.fiscal_year,
    w.fiscal_week,
    i.subcategory,
    cast(sum(s.units) as bigint) as net_units,
    cast(sum(s.net_sales) as decimal(18, 2)) as net_sales,
    cast(sum(s.gross_profit_before_funding) as decimal(18, 2)) as gross_profit_before_funding,
    cast(sum(s.promo_discount) as decimal(18, 2)) as promo_discount,
    count(distinct s.store_id) as reporting_stores
from {{ ref('fct_sales') }} as s
join {{ ref('dim_item') }} as i using (sku_id)
join {{ ref('dim_week') }} as w using (week_key)
group by all
