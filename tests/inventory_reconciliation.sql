-- Accepted inventory rows reach the fact one for one: none dropped, none duplicated.
select 'row_count_mismatch' as failure
where
    (select count(*) from {{ ref('fct_inventory') }})
    != (
        select count(*) from {{ ref('stg_inventory_audit') }}
        where disposition = 'accepted'
    )
