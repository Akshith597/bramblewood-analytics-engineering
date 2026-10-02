select *
from {{ ref('fct_vendor_claims') }}
where scan_amount_billed + display_fee_billed != total_billed or amount_collected > total_billed
