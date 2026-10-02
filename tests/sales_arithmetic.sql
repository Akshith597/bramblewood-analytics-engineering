select * from {{ ref('fct_sales') }}
where gross_sales - promo_discount != net_sales
