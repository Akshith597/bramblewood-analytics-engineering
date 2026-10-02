select
    cast(promo_id as varchar) as promo_id,
    cast(sku_id as varchar) as sku_id,
    cast(vendor_id as varchar) as vendor_id,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    cast(mechanic as varchar) as mechanic,
    cast(offer as varchar) as offer,
    cast(promo_price as decimal(18, 2)) as promo_price,
    cast(store_scope as varchar) as store_scope,
    cast(display as varchar) as display,
    cast(circular_feature as varchar) as circular_feature,
    cast(vendor_scan_per_unit as decimal(18, 2)) as vendor_scan_per_unit,
    cast(vendor_display_fee as decimal(18, 2)) as vendor_display_fee,
    cast(status as varchar) as status,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'promotions') }}
