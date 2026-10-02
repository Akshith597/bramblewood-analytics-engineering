select
    cast(store_id as integer) as store_id,
    sku_id,
    fiscal_week as week_key,
    cast(receipts_units as integer) as receipts_units,
    cast(on_hand_eow as integer) as on_hand_eow,
    _source_file,
    _source_row
from {{ source('raw', 'store_inventory_weekly') }}
