select
    promo_id,
    count(*) as claim_count,
    cast(sum(total_billed) as decimal(18, 2)) as total_billed,
    cast(sum(amount_collected) as decimal(18, 2)) as amount_collected,
    cast(sum(scan_amount_billed) as decimal(18, 2)) as scan_amount_billed,
    cast(sum(display_fee_billed) as decimal(18, 2)) as display_fee_billed
from {{ ref('stg_vendor_claims') }}
group by promo_id
