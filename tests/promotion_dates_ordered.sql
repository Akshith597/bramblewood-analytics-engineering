-- Every consumer of stg_promotions must see an ordered window; swapped source dates are reordered and flagged.
select promo_id, start_date, end_date, dates_swapped
from {{ ref('stg_promotions') }}
where
    start_date > end_date
    or dates_swapped != (source_start_date > source_end_date)
