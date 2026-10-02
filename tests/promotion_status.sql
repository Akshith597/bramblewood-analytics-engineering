select * from {{ ref('stg_promotions') }}
where status not in ('Approved', 'Cancelled') or status is null
