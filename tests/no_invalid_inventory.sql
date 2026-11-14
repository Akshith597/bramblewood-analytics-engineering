-- Every inventory row that is not loaded is returned with its source row and the reason it was excluded.
select
    _source_file,
    _source_row,
    disposition,
    source_store_id,
    source_sku_id,
    source_fiscal_week,
    source_receipts_units,
    source_on_hand_eow
from {{ ref('stg_inventory_audit') }}
where disposition != 'accepted'
