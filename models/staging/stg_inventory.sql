select
    cast(store_id as integer) as store_id,
    sku_id,
    fiscal_week as week_key,
    -- A blank quantity becomes null here so fct_inventory's not-null contract rejects it by name.
    cast(nullif(trim(receipts_units), '') as integer) as receipts_units,
    cast(nullif(trim(on_hand_eow), '') as integer) as on_hand_eow,
    _source_file,
    _source_row
from {{ source('raw', 'store_inventory_weekly') }}
