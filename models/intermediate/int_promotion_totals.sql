select
    promo_id,
    count(*) as eligible_sales_rows,
    cast(sum(case when eligible_event_count = 1 then units else 0 end) as bigint) as unambiguous_eligible_units,
    count(*) filter (where eligible_event_count > 1) as ambiguous_sales_rows,
    count(*) filter (where promo_discount > 0) as discounted_sales_rows
from {{ ref('int_promotion_sales') }}
group by promo_id
