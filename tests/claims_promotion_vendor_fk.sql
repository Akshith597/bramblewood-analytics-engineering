select c.*
from {{ ref('fct_vendor_claims') }} as c
left join {{ ref('stg_promotions') }} as p on c.promo_id = p.promo_id
where p.promo_id is null or c.vendor_id != p.vendor_id
