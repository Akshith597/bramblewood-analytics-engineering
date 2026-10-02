select
    store_id,
    normalized_upc as upc,
    parsed_week_ending as week_ending,
    parsed_units as units,
    parsed_gross_sales as gross_sales,
    parsed_promo_discount as promo_discount,
    parsed_net_sales as net_sales,
    _source_file,
    _source_row
from {{ ref('stg_pos_audit') }}
where disposition = 'accepted'
