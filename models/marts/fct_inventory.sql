select
    md5(concat_ws('|', store_id, sku_id, week_key)) as inventory_key,
    store_id,
    sku_id,
    week_key,
    receipts_units,
    on_hand_eow,
    _source_file,
    _source_row,
    on_hand_eow = 0 as zero_stock_snapshot
from {{ ref('stg_inventory') }}
