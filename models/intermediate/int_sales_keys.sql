select
    p.store_id,
    p.upc,
    p.week_ending,
    p.units,
    p.gross_sales,
    p.promo_discount,
    p.net_sales,
    p._source_file,
    p._source_row,
    i.sku_id,
    w.week_key,
    w.fiscal_year,
    s.price_zone,
    s.store_id is not null as store_key_matched,
    p.week_ending >= s.open_date as store_open,
    coalesce(p.week_ending between s.remodel_start and s.remodel_end, false) as remodel_week
from {{ ref('int_pos_accepted') }} as p
left join {{ ref('stg_items') }} as i on p.upc = i.upc
left join {{ ref('stg_fiscal_calendar') }} as w on p.week_ending = w.week_ending
left join {{ ref('stg_stores') }} as s on p.store_id = s.store_id
