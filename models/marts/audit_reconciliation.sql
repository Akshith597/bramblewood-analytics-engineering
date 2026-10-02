select
    disposition,
    count(*) as source_rows,
    cast(sum(parsed_net_sales) as decimal(18, 2)) as net_sales,
    cast(sum(parsed_units) as bigint) as units
from {{ ref('stg_pos_audit') }}
group by disposition
