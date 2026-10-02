select
    cast(vendor_id as varchar) as vendor_id,
    cast(vendor_name as varchar) as vendor_name,
    cast(payment_terms as varchar) as payment_terms,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'vendors') }}
