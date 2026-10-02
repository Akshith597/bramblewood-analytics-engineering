select * from {{ ref('fct_inventory') }}
where on_hand_eow < 0 or receipts_units < 0
