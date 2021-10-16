#!/usr/bin/env python

import sys
from pathlib import Path

sys.path.insert(0, Path(__file__).resolve().parents[1].joinpath('lib').as_posix())
import _venv  # This will activate the venv, if it exists and is not already active

import logging

from d2ro.cli import ArgParser, get_path
from d2ro.save_file import CTLOFile

log = logging.getLogger(__name__)


def parser():
    parser = ArgParser(description='Diablo II Remastered Save File Manager')
    # region View/Edit Options
    view_parser = parser.add_subparser('action', 'view', 'View information from a save file')

    _parsers = [parser, view_parser]

    view_info = view_parser.add_subparser('item', 'info')
    _parsers.append(view_info)

    view_attr = view_parser.add_subparser('item', 'attrs', 'View SaveFile attributes')
    _parsers.append(view_attr)

    for _parser in (view_attr,):
        _parser.add_argument('attr', nargs='*', help='The attribute(s) to view')
        _parser.add_argument('--binary', '-b', action='store_true', help='Show the binary version, even if a higher level representation is available')
        _parser.add_argument('--unknowns', '-u', action='store_true', help='Include unknown fields in output')
        _parser.add_argument('--no_sort', '-S', dest='sort_keys', action='store_false', help='Do not sort keys in output')
        view_bin_group = _parser.add_argument_group('Binary Data Options', 'Options that apply when viewing binary data')
        view_bin_group.add_argument('--per_line', '-L', type=int, default=8, help='Number of bytes to print per line')
        view_bin_group.add_argument('--hide_empty', '-e', type=int, default=10, help='Line threshold above which repeated lines of zeros will be hidden')

    for _parser in _parsers:
        mgroup = _parser.add_mutually_exclusive_group()
        mgroup.add_argument('--path', '-p', help='Save file path')
        mgroup.add_argument('--character', '-c', help='Character to view')
        _parser.add_argument('--verbose', '-v', action='store_true', help='Increase logging verbosity')

    # endregion

    # region Diff Options
    diff_parser = parser.add_subparser('action', 'diff', 'View the difference between 2 save files/slots')
    diff_files = diff_parser.add_subparser('item', 'files', 'View the difference between 2 save files')
    diff_files.add_argument('paths', nargs=2, help='The save files to process')
    diff_files.add_argument('--verbose', '-v', action='store_true', help='Increase logging verbosity')

    for _parser in (diff_files,):
        _group = _parser.add_argument_group('Diff Options')
        _group.add_argument('--per_line', '-L', type=int, default=8, help='Number of bytes to print per line (binary data only)')
        _group.add_argument('--binary', '-b', action='store_true', help='Show the binary version, even if a higher level representation is available')
        _fields = _parser.add_argument_group('Field Options').add_mutually_exclusive_group()
        _fields.add_argument('--keys', '-k', nargs='+', help='Specific keys/attributes to include in the diff (default: all)')
        _fields.add_argument('--unknowns', '-u', action='store_true', help='Only show unknown fields in output')
    # endregion
    return parser


def main():
    args = parser().parse_args()
    log_fmt = '%(asctime)s %(levelname)s %(name)s %(lineno)d %(message)s' if args.verbose else '%(message)s'
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format=log_fmt)

    if (action := args.action) in {'view', 'edit'}:
        game_data = CTLOFile.load(get_path(args.path, args.character))
        if action == 'view':
            view(game_data, args.item, args)
    elif action == 'diff':
        diff(args.item, args)
    else:
        raise ValueError(f'Unexpected action={args.action!r}')


def view(game_data: CTLOFile, item: str, args):
    if item in {'attrs', 'header'}:
        obj = game_data
        obj.pprint(
            args.unknowns,
            args.attr,
            binary=args.binary,
            per_line=args.per_line,
            hide_empty=args.hide_empty,
            sort_keys=args.sort_keys,
            struct=repr,
        )
    elif item == 'info':
        print(game_data)
    else:
        raise ValueError(f'Unexpected {item=} to view')


def diff(item: str, args):
    if item == 'files':
        obj_a, obj_b = CTLOFile.load(get_path(args.paths[0])), CTLOFile.load(get_path(args.paths[1]))
    else:
        raise ValueError(f'Unexpected {item=} to compare')

    if args.unknowns:
        keys = {k for k in obj_a._offsets_and_sizes if k.startswith('_unk')}
    else:
        keys = set(args.keys) if args.keys else None

    obj_a.diff(obj_b, per_line=args.per_line, byte_diff=args.binary, keys=keys, max_len=1)


if __name__ == '__main__':
    main()
