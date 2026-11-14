-- Preserve every source row, as stg_pos_audit does for sales. Nothing is cast with a hard `cast`: one malformed
-- value would abort the build with an unlabelled conversion error instead of naming the row.
with typed as (
    select
        store_id as source_store_id,
        sku_id as source_sku_id,
        fiscal_week as source_fiscal_week,
        receipts_units as source_receipts_units,
        on_hand_eow as source_on_hand_eow,
        _source_file,
        _source_row,
        try_cast(store_id as integer) as store_id,
        nullif(trim(sku_id), '') as sku_id,
        nullif(trim(fiscal_week), '') as week_key,
        try_cast(nullif(trim(receipts_units), '') as integer) as receipts_units,
        try_cast(nullif(trim(on_hand_eow), '') as integer) as on_hand_eow
    from {{ source('raw', 'store_inventory_weekly') }}
)

select
    *,
    case
        when source_store_id = 'store_id' and source_sku_id = 'sku_id' then 'embedded_header'
        when
            store_id is null or sku_id is null or week_key is null
            or not {{ regex_full_match('week_key', 'FY[0-9]{4}-W[0-9]{2}') }} then 'invalid_record'
        -- A blank quantity is a missing observation, not a zero and not a malformed number.
        when trim(source_receipts_units) = '' or trim(source_on_hand_eow) = '' then 'missing_quantity'
        when receipts_units is null or on_hand_eow is null then 'invalid_record'
        else 'accepted'
    end as disposition
from typed
