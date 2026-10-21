-- Null quantities would pass a plain "< 0" check, so an incomplete observation fails here too.
select * from {{ ref('fct_inventory') }}
where
    on_hand_eow < 0 or receipts_units < 0
    or on_hand_eow is null or receipts_units is null
