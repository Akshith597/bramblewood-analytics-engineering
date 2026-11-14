select
    store_id,
    sku_id,
    week_key,
    receipts_units,
    on_hand_eow,
    _source_file,
    _source_row
from {{ ref('stg_inventory_audit') }}
where disposition = 'accepted'
