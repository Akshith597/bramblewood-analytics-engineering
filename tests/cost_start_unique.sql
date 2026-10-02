select
    sku_id,
    effective_start
from {{ ref('stg_item_cost') }}
group by all
having count(*) > 1
