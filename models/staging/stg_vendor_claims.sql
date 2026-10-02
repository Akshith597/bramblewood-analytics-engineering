select
    cast(claim_id as varchar) as claim_id,
    cast(promo_id as varchar) as promo_id,
    cast(vendor_id as varchar) as vendor_id,
    cast(submitted_date as date) as submitted_date,
    cast(scan_units_billed as integer) as scan_units_billed,
    cast(scan_rate as decimal(18, 2)) as scan_rate,
    cast(scan_amount_billed as decimal(18, 2)) as scan_amount_billed,
    cast(display_fee_billed as decimal(18, 2)) as display_fee_billed,
    cast(total_billed as decimal(18, 2)) as total_billed,
    cast(status as varchar) as status,
    cast(amount_collected as decimal(18, 2)) as amount_collected,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'vendor_claims') }}
