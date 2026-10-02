select
    cast("table" as varchar) as source_table,
    cast("column" as varchar) as source_column,
    cast(definition as varchar) as definition,
    cast(_source_file as varchar) as _source_file,
    cast(_source_row as bigint) as _source_row
from {{ source('raw', 'data_dictionary') }}
