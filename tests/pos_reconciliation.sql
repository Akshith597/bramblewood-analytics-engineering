-- Sales reconcile to the accepted POS rows week by week. Comparing grand totals alone would let a row lost in one
-- week cancel against a row duplicated in another; each returned row names a week that does not tie out.
with loaded as (
    select
        week_ending,
        count(*) as sales_rows,
        sum(units) as units,
        sum(net_sales) as net_sales
    from {{ ref('fct_sales') }}
    group by week_ending
),

accepted as (
    select
        week_ending,
        count(*) as sales_rows,
        sum(units) as units,
        sum(net_sales) as net_sales
    from {{ ref('int_pos_accepted') }}
    group by week_ending
)

select
    coalesce(l.week_ending, a.week_ending) as week_ending,
    l.sales_rows as loaded_rows,
    a.sales_rows as accepted_rows,
    l.units as loaded_units,
    a.units as accepted_units,
    l.net_sales as loaded_net_sales,
    a.net_sales as accepted_net_sales
from loaded as l
full outer join accepted as a on l.week_ending = a.week_ending
where
    l.week_ending is null
    or a.week_ending is null
    or l.sales_rows != a.sales_rows
    or l.units != a.units
    or l.net_sales != a.net_sales
