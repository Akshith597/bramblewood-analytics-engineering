-- Owed is a calendar-based estimate, not a confirmed receivable.
with event_inputs as (
    select
        p.promo_id,
        p.sku_id,
        p.vendor_id,
        p.status,
        p.mechanic,
        p.store_scope,
        p.start_date,
        p.end_date,
        p.display,
        p.vendor_scan_per_unit,
        p.vendor_display_fee,
        coalesce(e.eligible_sales_rows, 0) as eligible_sales_rows,
        coalesce(e.unambiguous_eligible_units, 0) as unambiguous_eligible_units,
        coalesce(e.ambiguous_sales_rows, 0) as ambiguous_sales_rows,
        coalesce(e.discounted_sales_rows, 0) as discounted_sales_rows,
        coalesce(c.claim_count, 0) as claim_count,
        coalesce(c.scan_amount_billed, 0::decimal(18, 2)) as scan_amount_billed,
        coalesce(c.display_fee_billed, 0::decimal(18, 2)) as display_fee_billed,
        coalesce(c.total_billed, 0::decimal(18, 2)) as total_billed,
        coalesce(c.amount_collected, 0::decimal(18, 2)) as amount_collected
    from {{ ref('stg_promotions') }} as p
    left join {{ ref('int_promotion_totals') }} as e on p.promo_id = e.promo_id
    left join {{ ref('int_claim_totals') }} as c on p.promo_id = c.promo_id
),

estimates as (
    select
        *,
        cast(case
            when status = 'Cancelled' then 0
            when ambiguous_sales_rows > 0 then null
            else unambiguous_eligible_units * vendor_scan_per_unit
        end as decimal(18, 2)) as scan_funding_owed_estimate,
        cast(case
            when status = 'Approved' and display = 'Y' then vendor_display_fee
            else 0
        end as decimal(18, 2)) as display_funding_owed_estimate
    from event_inputs
),

funding as (
    select
        *,
        cast(scan_funding_owed_estimate + display_funding_owed_estimate as decimal(18, 2)) as funding_owed_estimate
    from estimates
)

select
    promo_id,
    sku_id,
    vendor_id,
    status,
    mechanic,
    store_scope,
    start_date,
    end_date,
    display,
    vendor_scan_per_unit,
    vendor_display_fee,
    eligible_sales_rows,
    unambiguous_eligible_units,
    ambiguous_sales_rows,
    discounted_sales_rows,
    claim_count,
    scan_funding_owed_estimate,
    display_funding_owed_estimate,
    funding_owed_estimate,
    scan_amount_billed,
    display_fee_billed,
    total_billed,
    amount_collected,
    cast(funding_owed_estimate - total_billed as decimal(18, 2)) as owed_minus_billed_estimate,
    cast(total_billed - amount_collected as decimal(18, 2)) as uncollected_billed_amount,
    cast(funding_owed_estimate - amount_collected as decimal(18, 2)) as owed_minus_collected_estimate,
    status = 'Approved' and claim_count = 0 as approved_without_claim,
    status = 'Cancelled' and claim_count > 0 as billed_on_cancelled_event,
    case
        when status = 'Cancelled' then 'cancelled'
        when ambiguous_sales_rows > 0 then 'ambiguous_event_assignment'
        when eligible_sales_rows = 0 then 'no_observed_sales'
        when discounted_sales_rows = 0 then 'no_discount_execution_signal'
        else 'calendar_based_estimate'
    end as funding_estimate_status
from funding
