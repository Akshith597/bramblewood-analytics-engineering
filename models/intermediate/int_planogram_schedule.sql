select
    sp.store_id,
    pg.sku_id,
    w.week_key,
    pg.facings,
    sp.planogram_id,
    contains(sp.planogram_id, 'TEST') as test_planogram
from {{ ref('stg_store_planogram') }} as sp
inner join {{ ref('stg_fiscal_calendar') }} as w
    on
        sp.effective_start <= w.week_ending
        and (sp.effective_end is null or sp.effective_end >= w.week_ending)
inner join {{ ref('stg_planograms') }} as pg
    on
        sp.planogram_id = pg.planogram_id
        and w.week_ending >= pg.effective_start
        and (pg.effective_end is null or w.week_ending <= pg.effective_end)
