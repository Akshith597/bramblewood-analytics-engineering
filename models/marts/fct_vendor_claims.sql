select
    claim_id,
    promo_id,
    vendor_id,
    submitted_date,
    scan_units_billed,
    scan_rate,
    scan_amount_billed,
    display_fee_billed,
    total_billed,
    status,
    amount_collected,
    cast(total_billed - amount_collected as decimal(18, 2)) as uncollected_billed_amount
from {{ ref('stg_vendor_claims') }}
