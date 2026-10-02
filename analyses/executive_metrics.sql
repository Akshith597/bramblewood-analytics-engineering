-- All-year revenue and list-cost margin. Returns remain signed.
select
    fiscal_year,
    sum(net_sales) as net_sales,
    sum(gross_profit_before_funding) as gross_profit_before_funding,
    sum(gross_profit_before_funding) / nullif(sum(net_sales), 0) as margin_rate
from {{ ref('fct_sales') }}
group by 1
order by 1;
