select c.*
from {{ ref('fct_vendor_claims') }} as c
left join {{ ref('stg_promotions') }} as p using (promo_id)
where p.promo_id is null or c.vendor_id != p.vendor_id
