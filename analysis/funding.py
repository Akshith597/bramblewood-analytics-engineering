"""Q5 — vendor funding owed vs billed vs collected (arithmetic with an assumption range). PLAN.md §Q5."""
from analysis.common import connect, round_floats, write_result

SQL = """
with events as (
    select p.promo_id, p.status, p.display,
        p.vendor_scan_per_unit::double * coalesce(t.unambiguous_eligible_units, 0) as scan_owed,
        case when p.display = 'Y' then p.vendor_display_fee::double else 0 end as display_owed,
        coalesce(c.scan_amount_billed, 0)::double as scan_billed,
        coalesce(c.display_fee_billed, 0)::double as display_billed,
        coalesce(c.total_billed, 0)::double as billed,
        coalesce(c.amount_collected, 0)::double as collected,
        coalesce(t.ambiguous_sales_rows, 0) as ambiguous_rows,
        coalesce(c.claim_count, 0) as claims
    from stg_promotions p
    left join int_promotion_totals t using (promo_id)
    left join int_claim_totals c using (promo_id)
)
select status, count(*) as events, sum(scan_owed), sum(display_owed), sum(scan_billed), sum(display_billed),
    sum(billed), sum(collected), sum(ambiguous_rows), count(*) filter (where claims = 0)
from events group by 1 order by 1
"""


def main():
    con = connect()
    keys = ['events', 'scan_owed', 'display_owed', 'scan_billed', 'display_billed', 'billed', 'collected',
            'ambiguous_rows', 'events_without_claim']
    by_status = {r[0]: dict(zip(keys, r[1:])) for r in con.execute(SQL).fetchall()}
    a = by_status['Approved']
    scan_gap = a['scan_owed'] - a['scan_billed']
    display_gap = a['display_owed'] - a['display_billed']
    result = {
        'by_status': by_status,
        'approved_gap_range': {
            'lower_scan_only': scan_gap,
            'upper_scan_plus_planned_display': scan_gap + display_gap,
            'display_component': display_gap,
            'note': 'Lower bound uses only scan-back on observed scoped units. The upper bound also assumes every '
                    'planned display ran; display execution is not observable in these extracts.'},
        'approved_billed_not_collected': a['billed'] - a['collected'],
        'cancelled_billed_not_collected': by_status.get('Cancelled', {}).get('billed', 0)
        - by_status.get('Cancelled', {}).get('collected', 0),
    }
    write_result('funding', round_floats(result))
    return result


if __name__ == '__main__':
    import json
    print(json.dumps(round_floats(main()), indent=1))
