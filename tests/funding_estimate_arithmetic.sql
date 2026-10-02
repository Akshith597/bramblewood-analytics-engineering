select *
from {{ ref('mart_promotion_funding') }}
where
    funding_owed_estimate != scan_funding_owed_estimate + display_funding_owed_estimate
    or owed_minus_billed_estimate != funding_owed_estimate - total_billed
    or uncollected_billed_amount != total_billed - amount_collected
    or owed_minus_collected_estimate != owed_minus_billed_estimate + uncollected_billed_amount
    or (ambiguous_sales_rows > 0 and status = 'Approved' and funding_owed_estimate is not null)
    or (status = 'Cancelled' and funding_owed_estimate != 0)
