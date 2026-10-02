select 'disposition_does_not_balance' as failure
where
    (select count(*) from {{ ref('stg_pos_audit') }})
    != (select sum(source_rows) from {{ ref('audit_reconciliation') }})
