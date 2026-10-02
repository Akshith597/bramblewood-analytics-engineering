select
    vendor_id,
    vendor_name,
    payment_terms
from {{ ref('stg_vendors') }}
