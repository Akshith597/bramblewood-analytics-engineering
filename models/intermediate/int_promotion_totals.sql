select
    promo_id,
    count(*) as eligible_sales_rows,
    cast(sum(case when eligible_event_count = 1 then units else 0 end) as bigint) as unambiguous_eligible_units,
    count(case when eligible_event_count > 1 then 1 end) as ambiguous_sales_rows,
    count(case when promo_discount > 0 then 1 end) as discounted_sales_rows
from {{ ref('int_promotion_sales') }}
group by promo_id
