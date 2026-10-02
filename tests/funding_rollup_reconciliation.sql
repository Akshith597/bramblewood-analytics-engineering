select 'claims_rollup_mismatch' as failure
where
    (select sum(total_billed) from {{ ref('fct_vendor_claims') }})
    != (select sum(total_billed) from {{ ref('mart_promotion_funding') }})
