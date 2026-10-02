"""Export small, reviewable SQL result sets and the actual dbt validation receipt."""
from pathlib import Path
from collections import Counter
import json, shutil
import duckdb

ROOT = Path(__file__).resolve().parents[1]
QUERIES = {
    "reconciliation": "select * from audit_reconciliation order by disposition",
    "annual_metrics": """select fiscal_year, count(*) as sales_rows, sum(units) as net_units,
        sum(net_sales) as net_sales, sum(gross_profit_before_funding) as gross_profit_before_funding,
        sum(gross_profit_before_funding)/sum(net_sales) as gross_margin_rate
        from fct_sales group by 1 order by 1""",
    "availability_coverage": """select has_sales_record, has_inventory_record, count(*) as records
        from mart_availability group by 1,2 order by 1,2""",
    "forecast_metrics": """select w.fiscal_year, count(*) as forecast_rows,
        count(*) filter (where f.has_actual) as matched_rows,
        sum(f.absolute_error_units)/nullif(sum(abs(f.actual_units)),0) as wape,
        sum(f.error_units)/nullif(sum(abs(f.actual_units)),0) as bias,
        count(*) filter (where f.lead_weeks != 2) as non_two_week_lead_rows
        from mart_forecast_accuracy f join dim_week w using(week_key) group by 1 order by 1""",
    "funding_by_vendor": """select v.vendor_name, count(*) as claims, sum(c.total_billed) as billed,
        sum(c.amount_collected) as collected, sum(c.uncollected_billed_amount) as uncollected
        from fct_vendor_claims c join dim_vendor v using(vendor_id) group by 1 order by uncollected desc""",
    "promotion_review": """select status, count(*) as events,
        count(*) filter (where approved_without_claim) as approved_without_claim,
        sum(coalesce(ambiguous_sales_rows,0)) as ambiguous_event_sales_rows
        from mart_promotion_funding group by 1 order by 1""",
    "cost_overlap": """select sku_id, effective_start, source_effective_end, effective_end,
        unit_cost from int_item_cost_intervals where overlap_adjusted order by sku_id""",
    "cost_policy_sensitivity": """select count(*) as affected_sales_rows, sum(s.units) as affected_net_units,
        sum(s.estimated_cogs-s.units*c.unit_cost) as cogs_increase_vs_prior_cost
        from fct_sales s join int_item_cost_intervals c on s.sku_id=c.sku_id and c.overlap_adjusted
        and s.week_ending > c.effective_end and s.week_ending <= c.source_effective_end""",
    "sample_store_week": """select s.sku_id, s.units, s.net_sales, s.unit_cost, s.estimated_cogs,
        s.gross_profit_before_funding, s._source_row
        from fct_sales s where store_id=101 and week_key='FY2024-W01' order by sku_id""",
    "quality_observations": """select
        (select count(*) from stg_pos where units<0) as return_rows,
        (select count(*) from stg_pos_audit where disposition='accepted' and length(upc)=11) as upcs_padded,
        (select count(*) from stg_pos_audit where disposition='accepted' and contains(week_ending,'/')) as legacy_dates,
        (select count(*) from fct_inventory where zero_stock_snapshot) as zero_stock_snapshots,
        (select max(submitted_date) from fct_vendor_claims) as latest_claim_submission""",
    "funding_waterfall": """select status, count(*) as events,
        sum(scan_funding_owed_estimate) as scan_owed_estimate,
        sum(display_funding_owed_estimate) as display_owed_estimate,
        sum(funding_owed_estimate) as funding_owed_estimate,
        sum(total_billed) as total_billed, sum(amount_collected) as amount_collected,
        sum(owed_minus_billed_estimate) as owed_minus_billed_estimate,
        sum(uncollected_billed_amount) as uncollected_billed_amount,
        sum(owed_minus_collected_estimate) as owed_minus_collected_estimate,
        count(*) filter (where funding_owed_estimate is null) as ambiguous_owed_events
        from mart_promotion_funding group by status order by status""",
    "funding_estimates_by_vendor": """select v.vendor_name,
        sum(m.funding_owed_estimate) as funding_owed_estimate,
        sum(m.total_billed) as total_billed, sum(m.amount_collected) as amount_collected,
        sum(m.owed_minus_billed_estimate) as owed_minus_billed_estimate,
        sum(m.owed_minus_collected_estimate) as owed_minus_collected_estimate
        from mart_promotion_funding m join dim_vendor v using(vendor_id)
        where m.status = 'Approved' group by 1 order by owed_minus_billed_estimate desc""",
    "funding_exception_queue": """select promo_id, vendor_id, status, funding_estimate_status,
        funding_owed_estimate, total_billed, amount_collected, owed_minus_billed_estimate,
        approved_without_claim, billed_on_cancelled_event
        from mart_promotion_funding
        where approved_without_claim or billed_on_cancelled_event or funding_estimate_status != 'calendar_based_estimate'
        order by status, owed_minus_billed_estimate desc, promo_id""",
    "funding_assumption_sensitivity": """select funding_estimate_status, count(*) as events,
        sum(funding_owed_estimate) as funding_owed_estimate,
        sum(owed_minus_billed_estimate) as owed_minus_billed_estimate
        from mart_promotion_funding where status='Approved'
        group by 1 order by 1""",
}

def main():
    evidence=ROOT/'evidence'; evidence.mkdir(exist_ok=True)
    result={}
    with duckdb.connect(str(ROOT/'warehouse/bramblewood.duckdb'),read_only=True) as con:
        for name,query in QUERIES.items():
            frame=con.execute(query).df()
            frame.to_csv(evidence/f'{name}.csv',index=False)
            result[name]=json.loads(frame.to_json(orient='records',date_format='iso'))
    runs=json.loads((ROOT/'evidence/dbt_build_results.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'target/manifest.json').read_text(encoding='utf-8'))
    tests=[r for r in runs['results'] if r['unique_id'].startswith(('test.','unit_test.'))]
    result['validation']={'dbt_version':runs['metadata']['dbt_version'],
        'generated_at':runs['metadata']['generated_at'],
        'models':len([n for n in manifest['nodes'].values() if n['resource_type']=='model']),
        'tests':len(tests),'test_statuses':dict(Counter(r['status'] for r in tests)),
        'all_statuses':dict(Counter(r['status'] for r in runs['results']))}
    (evidence/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (evidence/'queries.json').write_text(json.dumps(QUERIES,indent=2),encoding='utf-8')
    shutil.copyfile(ROOT/'warehouse/load_manifest.json',evidence/'load_manifest.json')
    print(json.dumps(result['validation'],indent=2))

if __name__=='__main__': main()
