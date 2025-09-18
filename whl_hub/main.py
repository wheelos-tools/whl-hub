import argparse
import sys
import logging
from whl_hub.manager import AssetManager


def main(args=sys.argv):
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    parser = argparse.ArgumentParser(
        description="WHL-Hub: Unified management tool for WheelOS models and maps.",
        prog="whl-hub"
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands', required=True)

    # --- list ---
    list_parser = subparsers.add_parser('list', help='List all installed models and maps.')

    # --- info ---
    info_parser = subparsers.add_parser('info', help='Show detailed information about an asset (model or map).')
    info_parser.add_argument('asset_name', help='The name of the asset.')

    # --- install ---
    install_parser = subparsers.add_parser('install', help='Install a new asset.')
    install_parser.add_argument('path', help='Path to the asset package (e.g., .whl or .zip).')

    install_parser.add_argument(
        '-t', '--type',
        choices=['model', 'map'],
        required=True,
        help="The type of the asset to install."
    )
    install_parser.add_argument('-s', '--skip', action='store_true', help='Skip if a version already exists.')

    # --- remove ---
    remove_parser = subparsers.add_parser('remove', help='Remove an installed asset.')
    remove_parser.add_argument('asset_name', help='The name of the asset to remove.')

    parsed_args = parser.parse_args(args[1:])
    logging.debug(f"Parsed args: {parsed_args}")

    # --- Logical dispatcher ---
    manager = AssetManager()

    if parsed_args.command == "list":
        manager.list_all()
    elif parsed_args.command == "info":
        manager.info(parsed_args.asset_name)
    elif parsed_args.command == "install":
        manager.install(parsed_args.path, parsed_args.type, parsed_args.skip)
    elif parsed_args.command == "remove":
        manager.remove(parsed_args.asset_name)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
