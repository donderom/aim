from asp import Run, Metric
from itertools import groupby
from collections.abc import MutableMapping
import math

if 'hash' in session_state:
    hash = session_state['hash']
else:
    hash = None


@memoize
def memoize_query(cb, query):
    return cb(query)


runs = memoize_query(Run.filter, f'c.hash=="{hash}"')
run = None

if runs:
    run = runs[0]
    ui.subheader(f'Run: {run["hash"]}')
else:
    ui.subheader('No runs found')
    ui.board_link('runs.py', 'Explore runs')


@memoize
def flatten(dictionary, parent_key='', separator='.'):
    flattened = {}
    for key, value in dictionary.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        if isinstance(value, MutableMapping):
            flattened.update(flatten(value, new_key, separator=separator))
        else:
            flattened[new_key] = value
    return flattened


@memoize
def merge_dicts(dict1, dict2):
    merged_dict = dict1.copy()
    merged_dict.update(dict2)
    return merged_dict


if run:
    params_tab, metrics_tab = ui.tabs(('Params', 'Metrics'))

    with params_tab:
        params = run['params']
        if params:
            ui.json(params)
        else:
            ui.text('No parameters found')

    with metrics_tab:
        metrics = memoize_query(Metric.filter, f'c.hash=="{hash}"')
        if metrics:
            row_controls, = ui.rows(1)
            group_fields = row_controls.multi_select(
                'Group by:', ('name', 'context', 'context.subset', 'hash'))
            metrics_processed = [merge_dicts(
                metric, flatten(metric)) for metric in metrics]

            def key_func(x): return tuple(
                str(x[field]) for field in group_fields)

            grouped_iterator = groupby(
                sorted(metrics_processed, key=key_func), key_func)
            grouped_data = [list(group) for key, group in grouped_iterator]
            x_axis = row_controls.select('Align by:', ('steps', 'axis.epoch'))
            y_axis = 'values'
            grouped_data_length = len(grouped_data)
            column_count = row_controls.number_input(
                'Columns:', value=2, min=1, max=grouped_data_length)
            rows = ui.rows(math.ceil(grouped_data_length/column_count))
            for i, row in enumerate(rows):
                cols = row.columns(column_count)
                for j, col in enumerate(cols):
                    col.html('<br />')
                    data_index = i*column_count+j
                    if data_index < grouped_data_length:
                        data = grouped_data[data_index]
                        for group_field in group_fields:
                            col.text(f'{group_field}: {data[0][group_field]}')
                        col.line_chart(
                            data, x=x_axis, y=y_axis, color=['name'])
        else:
            ui.text(f'No metrics found')
