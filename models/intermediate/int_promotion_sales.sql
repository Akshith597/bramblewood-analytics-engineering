-- Calendar eligibility is an estimate of execution; ambiguity is preserved.
select
    p.promo_id,
    s.sales_key,
    s.store_id,
    s.sku_id,
    s.week_key,
    s.units,
    s.net_sales,
    s.promo_discount,
    count(*) over (partition by s.sales_key) as eligible_event_count
from {{ ref('stg_promotions') }} as p
inner join {{ ref('int_sales_enriched') }} as s
    on
        p.sku_id = s.sku_id
        and s.week_ending between p.start_date and p.end_date
        and (p.store_scope = 'ALL' or p.store_scope = 'ZONE:' || s.price_zone)
where p.status = 'Approved'
