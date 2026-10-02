-- Full outer join preserves missing observations; absence never means zero.
select
    coalesce(s.store_id, i.store_id) as store_id,
    coalesce(s.sku_id, i.sku_id) as sku_id,
    coalesce(s.week_key, i.week_key) as week_key,
    s.sales_key is not null as has_sales_record,
    i.inventory_key is not null as has_inventory_record,
    s.units,
    s.net_sales,
    i.on_hand_eow,
    i.receipts_units,
    i.zero_stock_snapshot
from {{ ref('fct_sales') }} as s full outer join {{ ref('fct_inventory') }} as i
    on s.store_id = i.store_id and s.sku_id = i.sku_id and s.week_key = i.week_key
