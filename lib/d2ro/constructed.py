"""
Higher level classes for working with Diablo II Remastered save files.

:author: Doug Skrypa
"""

import logging
from functools import reduce
from operator import xor
from typing import Union, Optional, Collection

from construct import Struct, Bytes
from construct.lib.containers import ListContainer, Container

from .diff import pseudo_json_diff, unified_byte_line_diff
from .utils import to_hex_and_str, pseudo_json, colored, cached_classproperty, without_unknowns

__all__ = ['Constructed']
log = logging.getLogger(__name__)


class Field:
    def __init__(self, offset: int, struct):
        self.offset = offset
        self.struct = struct
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name


class SparseStruct:
    size: int
    align: int
    fields: dict[int, tuple[str, Struct]]

    def __init_subclass__(cls, size: int, align: int = 4):  # noqa
        cls.size = size
        cls.align = align
        cls.fields = {
            attr.offset: (attr.name, attr.struct) for name in dir(cls) if isinstance(attr := getattr(cls, name), Field)
        }

    def __new__(cls):
        struct_dict = {}
        pos = 0
        for offset, (name, struct) in sorted(cls.fields.items()):
            if pos != offset:
                pos = cls._fill_in(struct_dict, pos, offset)

            struct_dict[name] = struct
            pos += struct.sizeof()

        if pos < cls.size:
            cls._fill_in(struct_dict, pos, cls.size)

        # for k, v in struct_dict.items():
        #     log.debug(f'{k} = {v}, {v.sizeof()}')

        struct = Struct(*(k / v for k, v in struct_dict.items()))
        assert struct.sizeof() == cls.size
        return struct

    @classmethod
    def _fill_in(cls, struct_dict, pos: int, offset: int):
        fill = offset - pos
        if fill > cls.align:
            if fill % cls.align != 0:
                partial = fill - (fill // cls.align * cls.align)
                struct_dict[f'_unk_{pos}'] = Bytes(partial)
                pos += partial

            while pos < offset:
                struct_dict[f'_unk_{pos}'] = Bytes(cls.align)
                pos += cls.align
        else:
            struct_dict[f'_unk_{pos}'] = Bytes(fill)
            pos = offset
        return pos


class Constructed:
    def __init_subclass__(cls, construct):  # noqa
        cls._construct = construct

    def __init__(self, data: bytes, parsed=None):
        self._data = data
        self._parsed = parsed or self._construct.parse(data)

    def __getitem__(self, key: str):
        return _clean(self._parsed[key])

    __getattr__ = __getitem__

    def __setitem__(self, key: str, value):
        self._parsed[key] = value

    def __eq__(self, other: 'Constructed') -> bool:
        return self._data == other._data

    def __hash__(self):
        return reduce(xor, map(hash, (self.__class__, self._data)))

    @cached_classproperty
    def _offsets_and_sizes(cls):
        offsets_and_sizes = {}
        offset = 0
        for subcon in cls._construct.subcons:
            size = subcon.sizeof()  # TODO: Handle arrays differently?
            offsets_and_sizes[subcon.name] = (offset, size)
            offset += size
        return offsets_and_sizes

    def _build(self):
        return _build(self._parsed)

    def raw(self, key: str) -> bytes:
        offset, size = self._offsets_and_sizes[key]
        return self._data[offset: offset + size]  # noqa

    def raw_items(self):
        for key, (offset, size) in self._offsets_and_sizes.items():
            yield key, self._data[offset: offset + size]

    def diff(
        self,
        other: 'Constructed',
        *,
        max_len: Optional[int] = 30,
        per_line: int = 20,
        byte_diff: bool = False,
        keys: Collection[str] = None,
    ):
        row_keys = {'quests', 'quests_b'}
        found_difference = False
        for key, own_raw in self.raw_items():
            if (keys and key not in keys) or ((other_raw := other.raw(key)) == own_raw):
                continue
            if not found_difference:
                found_difference = True
                print(f'--- {self}\n+++ {other}')

            own_val = self[key]
            if not byte_diff and own_val != own_raw and not isinstance(own_val, (float, int, str)):
                print(colored(f'@@ {key} @@', 6))
                pseudo_json_diff(own_val, other[key], key in row_keys, key)
            elif max_len and isinstance(own_val, bytes) and len(own_raw) > max_len:
                unified_byte_line_diff(own_raw, other_raw, lineterm=key, struct=repr, per_line=per_line)
                # unified_byte_diff(own_raw, other_raw, lineterm=key, struct=repr, per_line=per_line)
            else:
                print(colored(f'@@ {key} @@', 6))
                print(colored(f'- {own_val}', 1))
                print(colored(f'+ {other[key]}', 2))

    def view(self, key: str, per_line: int = 40, hide_empty: Union[bool, int] = 10, **kwargs):
        data = self.raw(key)
        if isinstance(hide_empty, int):
            hide_empty = (len(data) / per_line) > hide_empty

        offset_fmt = '0x{{:0{}X}}:'.format(len(hex(len(data))) - 2)
        nul = b'\x00' * per_line
        last_os = len(data) // per_line
        is_empty, need_ellipsis = False, True
        for offset in range(0, len(data), per_line):
            nxt = offset + per_line
            line = data[offset:nxt]
            if hide_empty:
                was_empty = is_empty
                if (is_empty := line == nul) and was_empty and offset != last_os and data[nxt: nxt + per_line] == nul:
                    if need_ellipsis:
                        print('...')
                        need_ellipsis = False
                    continue

            need_ellipsis = True
            print(to_hex_and_str(offset_fmt.format(offset), line, fill=per_line, **kwargs))

    def view_unknowns(self, per_line: int = 40, hide_empty: Union[bool, int] = 10, **kwargs):
        for key in self._offsets_and_sizes:
            if key.startswith('_unk'):
                print(colored('\n{}  {}  {}'.format('=' * 30, key, '=' * 30), 14))
                self.view(key, per_line, hide_empty, **kwargs)

    def _pprint(self, key: str, val, sort_keys: bool = True, unknowns: bool = False):
        if isinstance(val, dict):
            val = pseudo_json(val if unknowns else without_unknowns(val), sort_keys=sort_keys)
        print(f'{colored(key, 14)}: {val}')

    def pprint(
        self,
        unknowns: bool = False,
        keys: Collection[str] = None,
        binary: bool = False,
        sort_keys: bool = True,
        **kwargs,
    ):
        last_was_view = False
        for key in self._offsets_and_sizes:
            if (keys and key not in keys) or (not unknowns and key.startswith('_unk')):
                continue

            if binary:
                print(colored('\n{}  {}  {}'.format('=' * 30, key, '=' * 30), 14))
                self.view(key, **kwargs)
            else:
                val = self[key]
                if isinstance(val, bytes):
                    print(colored('\n{}  {}  {}'.format('=' * 30, key, '=' * 30), 14))
                    self.view(key, **kwargs)
                    last_was_view = True
                else:
                    if last_was_view:
                        print()
                    self._pprint(key, val, sort_keys=sort_keys, unknowns=unknowns)
                    last_was_view = False


def _build(obj):
    if isinstance(obj, ListContainer):
        return [_build(li) for li in obj]
    elif isinstance(obj, Container):
        if set(obj) == {'offset1', 'length', 'offset2', 'data', 'value'}:  # RawCopy
            return {'value': _build(obj.value)}
        return {key: _build(val) for key, val in obj.items() if key != '_io'}
    else:
        return obj


def _clean(obj):
    if isinstance(obj, ListContainer):
        return [_clean(li) for li in obj]
    elif isinstance(obj, Container):
        if set(obj) == {'offset1', 'length', 'offset2', 'data', 'value'}:  # RawCopy
            return _clean(obj.value)
        return {key: _clean(val) for key, val in obj.items() if key not in ('_io', '_flagsenum')}
    else:
        return obj
