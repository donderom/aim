import logging

from typing import TypeVar, Generic, Any, Optional, Dict, Union, Tuple, List, Set, Iterator, Callable

from aim._sdk import type_utils
from aim._sdk.utils import utc_timestamp
from aim._sdk.interfaces.sequence import Sequence as ABCSequence
from aim._sdk.query_utils import SequenceQueryProxy, ContainerQueryProxy
from aim._sdk.constants import KeyNames

from aim._sdk.context import Context, cached_context
from aim._sdk.query import RestrictedPythonQuery

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from aim._core.storage.treeview import TreeView
    from aim._sdk.container import Container
    from aim._sdk.collections import SequenceCollection
    from aim._sdk.storage_engine import StorageEngine
    from aim._sdk.repo import Repo

_ContextInfo = Union[Dict, Context, int]

logger = logging.getLogger(__name__)


class _SequenceInfo:
    def __init__(self, info_tree: 'TreeView'):
        self._meta_tree = info_tree

        self._initialized = False
        self.next_step = None
        self.version = None
        self.first_step = None
        self.last_step = None
        self.creation_time = None
        self.axis_names: Set[str] = set()
        self.dtype = None
        self.empty = None

    def preload(self):
        if self._initialized:
            return

        info = self._meta_tree.subtree(KeyNames.INFO_PREFIX)

        try:
            info.preload()
            self.version = info['version']
            self.first_step = info['first_step']
            self.last_step = info['last_step']
            self.creation_time = info['creation_time']
            self.axis_names = set(info['axis'])
            self.dtype = info[KeyNames.VALUE_TYPE]
            self.stype = info[KeyNames.SEQUENCE_TYPE]
            self.empty = False
            self.next_step = self.last_step + 1
        except KeyError:
            self.empty = True
            self.next_step = 0
        finally:
            self._initialized = True


ItemType = TypeVar('ItemType')


@type_utils.query_alias('sequence', 's')
@type_utils.auto_registry
class Sequence(Generic[ItemType], ABCSequence):
    version = '1.0.0'

    def __init__(self, container: 'Container', *, name: str, context: _ContextInfo):
        self.storage: StorageEngine = container.storage
        self._container: 'Container' = container
        self._container_hash: str = container.hash
        self._meta_tree = container._meta_tree
        self._container_tree = container._tree

        self._name = name

        self._ctx_idx: int = None
        self._context: Context = None
        self._init_context(context)

        self._data_loader: Callable[[], 'TreeView'] = container._data_loader
        self.__data = None

        self.__storage_init__()

    def __storage_init__(self):
        self._tree = self._container_tree.subtree((KeyNames.SEQUENCES, self._ctx_idx, self._name))

        self._values = None
        self._info = _SequenceInfo(self._tree)
        self._allowed_value_types = None

    @classmethod
    def from_storage(cls, storage, meta_tree: 'TreeView', *, hash_: str, name: str, context: _ContextInfo):
        self = cls.__new__(cls)
        self.storage = storage
        self._container = None
        self._container_hash = hash_
        self._meta_tree = meta_tree
        self._container_tree = meta_tree.subtree('chunks').subtree(hash_)

        self._name = name

        self._ctx_idx = None
        self._context = None
        self._init_context(context)

        self._data_loader = lambda: storage.tree(hash_, 'seqs', read_only=True).subtree('chunks').subtree(hash_)
        self.__data: TreeView = None

        self.__storage_init__()
        return self

    @classmethod
    def filter(cls, expr: str = '', repo: 'Repo' = None) -> 'SequenceCollection':
        if repo is None:
            from aim._sdk.repo import Repo
            repo = Repo.active_repo()
        return repo.sequences(query_=expr, type_=cls)

    def _init_context(self, context: _ContextInfo):
        if isinstance(context, int):
            self._ctx_idx = context
            self._context = None
        elif isinstance(context, dict):
            self._context = Context(context)
            self._ctx_idx = self._context.idx
        elif isinstance(context, Context):
            self._context = context
            self._ctx_idx = self._context.idx

    @property
    def name(self):
        return self._name

    @property
    def context(self) -> Dict:
        if self._context is None:
            self._context = self._context_from_idx(ctx_idx=self._ctx_idx)
        return self._context.to_dict()

    @cached_context
    def _context_from_idx(self, ctx_idx) -> Context:
        return Context(self._meta_tree[KeyNames.CONTEXTS, ctx_idx])

    @property
    def type(self) -> str:
        self._info.preload()
        return self._info.dtype

    @property
    def is_empty(self) -> bool:
        self._info.preload()
        return self._info.empty

    @property
    def start(self) -> int:
        self._info.preload()
        return self._info.first_step

    @property
    def stop(self) -> int:
        self._info.preload()
        return self._info.last_step

    @property
    def next_step(self) -> int:
        self._info.preload()
        return self._info.next_step

    def match(self, expr) -> bool:
        query = RestrictedPythonQuery(expr)
        query_cache = dict
        return self._check(query, query_cache)

    @property
    def axis_names(self) -> Tuple[str]:
        self._info.preload()
        return tuple(self._info.axis_names)

    def axis(self, name: str) -> Iterator[Any]:
        return map(lambda x: x.get(name, None), self._data.reservoir().values())

    def items(self) -> Iterator[Tuple[int, Any]]:
        return self._data.reservoir().items()

    def values(self) -> Iterator[Any]:
        for _, v in self.items():
            yield v['val']

    def sample(self, k: int) -> List[Any]:
        return self[:].sample(k)

    @property
    def allowed_value_types(self) -> Tuple[str]:
        if self._allowed_value_types is None:
            sequence_class = self.__sequence_class__
            self._allowed_value_types = type_utils.get_sequence_value_types(sequence_class)

        return self._allowed_value_types

    def track(self, value: Any, *, step: Optional[int] = None, **axis):
        value_type = type_utils.get_object_typename(value)
        if not type_utils.is_allowed_type(value_type, self.allowed_value_types):
            raise ValueError(f'Cannot track value \'{value}\' of type {type(value)}. Type is not supported.')

        self._info.preload()
        if step is None:
            step = self._info.next_step

        axis_names = set(axis.keys())
        with self.storage.write_batch(self._container_hash):
            if self._info.empty:
                self._tree[KeyNames.INFO_PREFIX, 'creation_time'] = utc_timestamp()
                self._tree[KeyNames.INFO_PREFIX, 'version'] = self.version
                self._tree[KeyNames.INFO_PREFIX, KeyNames.OBJECT_CATEGORY] = self.object_category
                self._tree[KeyNames.INFO_PREFIX, 'first_step'] = self._info.first_step = step
                self._tree[KeyNames.INFO_PREFIX, 'last_step'] = self._info.last_step = step
                self._tree[KeyNames.INFO_PREFIX, 'axis'] = tuple(axis_names)
                self._tree[KeyNames.INFO_PREFIX, KeyNames.VALUE_TYPE] = self._info.dtype = value_type
                self._tree[KeyNames.INFO_PREFIX, KeyNames.SEQUENCE_TYPE] = self.get_full_typename()

                self._meta_tree[KeyNames.CONTEXTS, self._ctx_idx] = self._context.to_dict()
                self._container_tree[KeyNames.CONTEXTS, self._ctx_idx] = self._context.to_dict()
                for typename in self.get_full_typename().split('->'):
                    self._meta_tree[KeyNames.SEQUENCES, typename, self._ctx_idx, self.name] = 1

                self._tree['first_value'] = value
                self._tree['last_value'] = value
                self._tree['axis_last_values'] = axis
                self._info.axis_names = axis_names
                self._info.empty = False

            if step > self._info.last_step:
                self._tree[KeyNames.INFO_PREFIX, 'last_step'] = self._info.last_step = step
                self._tree['last_value'] = value
                self._tree['axis_last_values'] = axis
            if step < self._info.first_step:
                self._tree[KeyNames.INFO_PREFIX, 'first_step'] = self._info.first_step = step
                self._tree['first_value'] = value
            if not type_utils.is_subtype(value_type, self._info.dtype):
                dtype = type_utils.get_common_typename((value_type, self._info.dtype))
                self._tree[KeyNames.INFO_PREFIX, KeyNames.VALUE_TYPE] = self._info.dtype = dtype
            if not axis_names.issubset(self._info.axis_names):
                self._info.axis_names.update(axis_names)
                self._tree[KeyNames.INFO_PREFIX, 'axis'] = tuple(self._info.axis_names)
            if self._values is None:
                self._values = self._data.reservoir()

            val = {k: v for k, v in axis.items()}
            val['val'] = value
            self._values[step] = val
            self._info.next_step = self._info.last_step + 1

    def __iter__(self) -> Iterator[Tuple[int, Tuple[Any, ...]]]:
        data_iterator = zip(self.items(), zip(map(self.axis, self.axis_names)))
        for (step, value), axis_values in data_iterator:
            yield step, (value,) + axis_values

    def __getitem__(self, item: Union[slice, str, Tuple[str]]) -> 'SequenceView':
        if isinstance(item, str):
            item = (item,)
        if isinstance(item, slice):
            columns = self.axis_names + ('val',)
            return SequenceView(self, columns=columns, start=item.start, stop=item.stop)
        elif isinstance(item, tuple):
            return SequenceView(self, columns=item)

    @property
    def _data(self) -> 'TreeView':
        if self.__data is None:
            self.__data = self._data_loader().subtree((self._ctx_idx, self._name))
        return self.__data

    @property
    def __sequence_class__(self):
        if hasattr(self, '__orig_class__'):
            return self.__orig_class__
        return self.__class__

    def _check(self, query, query_cache, *, aliases=()) -> bool:
        hash_ = self._container_hash
        proxy = SequenceQueryProxy(self.name, self._context_from_idx, self._ctx_idx, self._tree, query_cache[hash_])
        c_proxy = ContainerQueryProxy(hash_, self._container_tree, query_cache[hash_])

        if isinstance(aliases, str):
            aliases = (aliases,)
        alias_names = self.default_aliases.union(aliases)
        if self._container is not None:
            container_alias_names = self._container.default_aliases
        else:
            from aim._sdk.container import Container
            container_alias_names = Container.default_aliases

        query_params = {p: proxy for p in alias_names}
        query_params.update({cp: c_proxy for cp in container_alias_names})
        return query.check(**query_params)

    def __repr__(self) -> str:
        return f'<{self.get_typename()} #{hash(self)} name={self.name} context={self._ctx_idx}>'


class SequenceView(object):
    def __init__(self, sequence: Sequence, *, columns: Tuple[str], start: int = None, stop: int = None):
        self._start: int = start if start is not None else sequence._info.first_step
        self._stop: int = stop if stop is not None else sequence._info.next_step
        self._columns: Set[str] = set(columns)
        self._sequence = sequence

    @property
    def start(self) -> int:
        return self._start

    @property
    def stop(self) -> int:
        return self._stop

    @property
    def columns(self) -> Tuple[str]:
        return tuple(self._columns)

    def __getitem__(self, item: Union[slice, str, Tuple[str]]) -> 'SequenceView':
        if isinstance(item, str):
            item = (item,)
        if isinstance(item, slice):
            if self.start is not None and item.start is not None:
                start = max(self.start, item.start)
            else:
                start = self.start if item.start is None else item.start
            if self.stop is not None and item.stop is not None:
                stop = min(self.stop, item.stop)
            else:
                stop = self.stop if item.stop is None else item.stop
            return SequenceView(self._sequence, start=start, stop=stop, columns=self.columns)
        elif isinstance(item, tuple):
            columns = tuple(self._columns.intersection(item))
            return SequenceView(self._sequence, start=self.start, stop=self.stop, columns=columns)

    def sample(self, k: Optional[int] = None) -> List[Any]:
        def get_columns(item):
            return [item[0], {k: v for k, v in item[1].items() if k in self._columns}]
        if k is None:
            k = self.stop - self.start
        samples = self._sequence._data.reservoir().sample(k, begin=self.start, end=self.stop)
        return sorted(map(get_columns, samples), key=lambda x: x[0])
