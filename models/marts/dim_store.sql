select
    store_id,
    store_name,
    city,
    state,
    format,
    sqft,
    price_zone,
    pos_system,
    open_date,
    remodel_start,
    remodel_end
from {{ ref('stg_stores') }}
