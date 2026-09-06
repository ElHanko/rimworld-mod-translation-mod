#!/usr/bin/env python3
"""Small CLI dispatcher for the RimWorld translation workflow."""
import argparse
import importlib
import sys
import xml.etree.ElementTree as ET

import config


def install():
    link = config.LOCAL_MODS / 'ElHanko-German-Translations'
    if link.is_symlink():
        if link.resolve() == config.ROOT.resolve():
            print(f'Symlink bereits korrekt: {link}')
            return
        raise ValueError(f'{link} zeigt auf {link.resolve()}; keine Änderung vorgenommen')
    if link.exists():
        raise ValueError(f'{link} existiert und ist kein Symlink; keine Änderung vorgenommen')
    link.symlink_to(config.ROOT.resolve())
    print(f'Symlink angelegt: {link}')


def main(argv=None):
    parser = argparse.ArgumentParser(prog='./rwgt')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('refresh', 'status', 'build', 'verify', 'validate', 'install'):
        commands.add_parser(name)
    draft = commands.add_parser('draft')
    selection = draft.add_mutually_exclusive_group(required=True)
    selection.add_argument('package', nargs='?')
    selection.add_argument('--all', action='store_true')
    commands.add_parser('progress').add_argument('package', nargs='?')
    work = commands.add_parser('work')
    work.add_argument('package', nargs='?')
    work.add_argument('--next', action='store_true')
    work.add_argument('--limit', type=int, default=25)
    work.add_argument('--offset', type=int, default=0)
    commands.add_parser('apply').add_argument('file')
    args = parser.parse_args(argv)
    try:
        config.configure()
        if args.command == 'install':
            install()
        elif args.command == 'validate':
            from common import runtime_records
            print(f'XML-Validierung: ✓ ({len(runtime_records(config.LANG))} Einträge)')
        else:
            module = importlib.import_module(args.command)
            if args.command == 'draft':
                module.run('--all' if args.all else args.package)
            elif args.command == 'progress':
                module.run(args.package)
            elif args.command == 'work':
                if args.next and args.package:
                    raise ValueError('--next und PACKAGE-ID schließen sich aus')
                module.run(args.package, args.limit, args.offset)
            elif args.command == 'apply':
                module.run(args.file)
            else:
                module.run()
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f'FEHLER: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
