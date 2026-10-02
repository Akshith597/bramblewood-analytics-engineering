select
    sku_id,
    upc,
    description,
    brand,
    vendor_id,
    category,
    subcategory,
    brand_type,
    flavor,
    size_desc,
    size_oz,
    case_pack,
    launch_date,
    discontinue_date,
    replaces_sku,
    status
from {{ ref('stg_items') }}
