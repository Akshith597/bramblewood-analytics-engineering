select * from {{ ref('stg_pos_audit') }}
where disposition = 'invalid_record'
