select * from {{ ref('fct_sales') }}
where not store_open or not store_key_matched
