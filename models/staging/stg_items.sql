select
    cast(sku_id as varchar) as sku_id,
    {{ normalize_upc('upc') }} as upc,
    cast(description as varchar) as description,
    cast(brand as varchar) as brand,
    cast(vendor_id as varchar) as vendor_id,
    cast(category as varchar) as category,
    case when lower(trim(subcategory)) = 'tortilla chips' then 'Tortilla Chips' else trim(subcategory) end
        as subcategory,
    cast(brand_type as varchar) as brand_type,
    cast(flavor as varchar) as flavor,
    cast(size_desc as varchar) as size_desc,
    cast(size_oz as decimal(8, 2)) as size_oz,
    cast(case_pack as integer) as case_pack,
    cast(launch_date as date) as launch_date,
    cast(discontinue_date as date) as discontinue_date,
    cast(replaces_sku as varchar) as replaces_sku,
    cast(status as varchar) as status,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'items') }}
