-- Preserve every source row. Exact replays are ranked before normalization.
with ranked as (
    select
        *,
        row_number() over (
            partition by store_nbr, upc, week_ending, units, gross_sales, promo_discount, net_sales
            order by _source_row
        ) as replay_number
    from {{ source('raw', 'pos_weekly_sales') }}
),

typed as (
    select
        *,
        try_cast(store_nbr as integer) as store_id,
        {{ normalize_upc('upc') }} as normalized_upc,
        coalesce(
            {{ try_parse_date('week_ending', '%Y-%m-%d') }},
            {{ try_parse_date('week_ending', '%m/%d/%Y') }}
        ) as parsed_week_ending,
        try_cast(units as integer) as parsed_units,
        try_cast(gross_sales as decimal(18, 2)) as parsed_gross_sales,
        try_cast(promo_discount as decimal(18, 2)) as parsed_promo_discount,
        try_cast(net_sales as decimal(18, 2)) as parsed_net_sales
    from ranked
)

select
    *,
    case
        when store_nbr = 'store_nbr' and upc = 'upc' then 'embedded_header'
        when replay_number > 1 then 'exact_replay'
        when
            store_id is null or parsed_week_ending is null or parsed_units is null
            or parsed_gross_sales is null or parsed_promo_discount is null or parsed_net_sales is null
            or not {{ regex_full_match('trim(upc)', '[0-9]{11,12}') }} then 'invalid_record'
        else 'accepted'
    end as disposition
from typed
