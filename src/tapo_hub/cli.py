"""Command-line interface for reading Tapo H100 child devices."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import sys
from datetime import datetime
from getpass import getpass
from typing import Any

import keyring
from rich import box
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import load_config, save_config
from .credentials import (
    CredentialError,
    delete_password,
    get_password,
    save_password,
)
from .devices import get_measurement, redact_sensitive
from .service import HubError, read_hub

console = Console()
error_console = Console(stderr=True)


class AppError(RuntimeError):
    """A user-facing application error."""


def _validate_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise AppError(f"'{value}' is not a valid IP address.") from exc


def _add_root_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--help",
        action="help",
        help="show this help message and exit (use -h for humidity)",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--list", action="store_true", help="list hub child devices")
    output.add_argument(
        "-t", "--temperature", action="store_true", help="show temperature values"
    )
    output.add_argument(
        "-h", "--humidity", action="store_true", help="show humidity values"
    )
    parser.add_argument(
        "--hub-ip",
        metavar="IP",
        help="H100 IP address (overrides the saved configuration)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        metavar="SECONDS",
        help="repeat the query at this interval",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print machine-readable JSON instead of a formatted view",
    )
    parser.add_argument(
        "--short",
        "--raw",
        dest="raw",
        action="store_true",
        help="with -t/-h, print only numbers (one per sensor)",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tapo-hub",
        description="Read sensors and other child devices connected to a Tapo H100.",
        add_help=False,
    )
    _add_root_arguments(parser)
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")

    auth_parser = commands.add_parser(
        "auth", help="manage Tapo credentials in the system keyring"
    )
    auth_commands = auth_parser.add_subparsers(dest="auth_command", required=True)

    setup_parser = auth_commands.add_parser("setup", help="save account credentials")
    setup_parser.add_argument("--username", help="Tapo account email")
    setup_parser.add_argument("--hub-ip", metavar="IP", help="H100 IP address")

    auth_commands.add_parser("status", help="show whether credentials are configured")
    auth_commands.add_parser("logout", help="remove saved credentials")

    gui_parser = commands.add_parser(
        "gui", help="open the local browser-based sensor dashboard"
    )
    gui_parser.add_argument("--port", type=int, default=8765, help="local port")
    gui_parser.add_argument(
        "--no-browser", action="store_true", help="do not open a browser automatically"
    )
    return parser


def _save_auth(username: str | None, hub_ip: str | None) -> None:
    config = load_config()
    username = (username or input("Tapo account email: ")).strip()
    if not username:
        raise AppError("The Tapo account email cannot be empty.")

    saved_ip = config.get("hub_ip")
    hub_ip = hub_ip or input(
        f"H100 IP address [{saved_ip or 'not set'}]: "
    ).strip() or saved_ip
    if not hub_ip:
        raise AppError("Set the H100 IP with --hub-ip.")
    hub_ip = _validate_ip(hub_ip)

    password = getpass("Tapo account password (saved only in system keyring): ")
    if not password:
        raise AppError("The password cannot be empty.")
    save_password(username, password)
    config.update({"username": username, "hub_ip": hub_ip})
    save_config(config)
    console.print(
        f"[green]Credentials saved in the system keyring.[/]\n"
        f"Account: {username}\nH100: {hub_ip}"
    )


def _auth_status() -> None:
    config = load_config()
    username = config.get("username")
    if not username:
        console.print("No Tapo account configured. Run [bold]tapo-hub auth setup[/].")
        return
    password = get_password(str(username))
    backend = keyring.get_keyring()
    if password:
        console.print(
            f"[green]Credentials are available.[/] Account: {username}\n"
            f"H100: {config.get('hub_ip', 'not configured')}\n"
            f"Keyring: {type(backend).__name__}"
        )
    else:
        console.print(
            f"No password found for {username}. Run [bold]tapo-hub auth setup[/]."
        )


def _auth_logout() -> None:
    config = load_config()
    username = config.get("username")
    if username:
        delete_password(str(username))
        config.pop("username", None)
        save_config(config)
    console.print("Saved Tapo credentials removed from the system keyring.")


def _display_name(record: dict[str, Any]) -> str:
    return str(record.get("name") or "Unnamed device")


def _display_inventory(records: list[dict[str, Any]], as_json: bool) -> None:
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "name": record["name"],
                        "model": record["model"],
                        "device_id": record["device_id"],
                    }
                    for record in records
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    table = Table(title="Devices connected to the H100", box=box.ROUNDED)
    table.add_column("Name", style="cyan")
    table.add_column("Model", style="magenta")
    table.add_column("Device ID", overflow="fold")
    for record in records:
        table.add_row(
            _display_name(record),
            str(record.get("model") or "Unknown"),
            str(record.get("device_id") or "—"),
        )
    console.print(table)
    console.print(f"{len(records)} device(s)")


def _display_all_data(
    records: list[dict[str, Any]], as_json: bool, hub_ip: str
) -> None:
    if as_json:
        print(
            json.dumps(
                redact_sensitive(records),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )
        return
    if not records:
        console.print(f"No child devices found on H100 at {hub_ip}.")
        return

    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    console.print(f"[dim]H100 {hub_ip} · updated {timestamp}[/]")
    for record in records:
        fields = Table.grid(padding=(0, 1))
        fields.add_column(style="bold cyan", no_wrap=True)
        fields.add_column(overflow="fold")
        fields.add_row("[bold]Device ID[/]", str(record.get("device_id") or "—"))

        api_data = redact_sensitive(record.get("api_data") or {})
        if api_data:
            fields.add_row(
                "[bold]All API fields[/]",
                JSON(json.dumps(api_data, ensure_ascii=False, indent=2, default=str)),
            )
        parsed_data = redact_sensitive(record.get("parsed_data") or {})
        if parsed_data:
            fields.add_row(
                "[bold]Decoded fields[/]",
                JSON(
                    json.dumps(
                        parsed_data, ensure_ascii=False, indent=2, default=str
                    )
                ),
            )

        console.print(
            Panel(
                fields,
                title=f"{_display_name(record)} · {record.get('model', 'Unknown')}",
                border_style="blue",
                box=box.ROUNDED,
            )
        )


def _display_measurements(
    records: list[dict[str, Any]],
    metric: str,
    as_json: bool,
    raw: bool,
) -> None:
    label = "temperature" if metric == "temperature" else "humidity"
    results: list[dict[str, Any]] = []
    for record in records:
        measurement = get_measurement(record, metric)
        if measurement is None:
            continue
        value, unit = measurement
        if isinstance(value, float):
            value = round(value, 1)
        results.append(
            {
                "name": _display_name(record),
                "value": value,
                "unit": unit or ("%" if metric == "humidity" else ""),
            }
        )

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif raw:
        for result in results:
            print(result["value"])
    elif not results:
        console.print(f"No {label} readings found.")
    else:
        table = Table(title=label.capitalize(), box=box.SIMPLE)
        table.add_column("Sensor", style="cyan")
        table.add_column("Value", justify="right", style="green")
        for result in results:
            suffix = f" {result['unit']}" if result["unit"] else ""
            table.add_row(result["name"], f"{result['value']}{suffix}")
        console.print(table)


async def _run_reader(args: argparse.Namespace) -> None:
    config = load_config()
    hub_ip = args.hub_ip or config.get("hub_ip")
    if not hub_ip:
        raise AppError("Set the H100 IP with 'tapo-hub auth setup --hub-ip IP'.")
    hub_ip = _validate_ip(hub_ip)
    if args.interval is not None and args.interval < 1:
        raise AppError("--interval must be at least 1 second.")
    if args.raw and not (args.temperature or args.humidity):
        raise AppError("--short can only be used with -t or -h.")
    if args.raw and args.json:
        raise AppError("--short cannot be combined with --json.")

    while True:
        records = await read_hub(hub_ip)
        if args.list:
            _display_inventory(records, args.json)
        elif args.temperature:
            _display_measurements(records, "temperature", args.json, args.raw)
        elif args.humidity:
            _display_measurements(records, "humidity", args.json, args.raw)
        else:
            _display_all_data(records, args.json, hub_ip)
        if args.interval is None:
            break
        await asyncio.sleep(args.interval)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        if args.command == "auth":
            if args.auth_command == "setup":
                _save_auth(args.username, args.hub_ip)
            elif args.auth_command == "status":
                _auth_status()
            elif args.auth_command == "logout":
                _auth_logout()
            return 0
        if args.command == "gui":
            from .gui import run_gui

            run_gui(args.port, open_browser=not args.no_browser)
            return 0
        asyncio.run(_run_reader(args))
        return 0
    except (AppError, CredentialError, HubError, ValueError) as exc:
        error_console.print(f"[red]Error:[/] {exc}")
        return 1
    except KeyboardInterrupt:
        console.print("\nStopped.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
