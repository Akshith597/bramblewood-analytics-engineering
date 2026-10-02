select 'row_count_or_money_mismatch' as failure
where
    (select count(*) from {{ ref('fct_sales') }}) != (select count(*) from {{ ref('int_pos_accepted') }})
    or (select sum(net_sales) from {{ ref('fct_sales') }}) != (select sum(net_sales) from {{ ref('int_pos_accepted') }})
    or (select sum(units) from {{ ref('fct_sales') }}) != (select sum(units) from {{ ref('int_pos_accepted') }})
