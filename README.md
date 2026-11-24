# Tapo Hub Reader

A local-first command-line tool for reading sensors and other child devices
connected to a TP-Link Tapo H100 hub. It shows all fields returned by the
hub's child-device API, including fields the Python client does not yet
interpret, and can print temperature or humidity readings by themselves.

> This is an unofficial community project, not affiliated with or endorsed by
> TP-Link. The H100 and Tapo are TP-Link trademarks.

## Features

- Discover and list child devices paired with an H100.
- Display the complete child-device data returned by the local API.
- Redact key/token/password fields in displayed and JSON output.
- Show temperature (`-t`) or humidity (`-h`) values, with a number-only
  `--short` mode.
- Launch a polished local browser dashboard with `tapo-hub gui`.
- Install the dashboard as a PWA in supported browsers on the computer running
  the local server.
- Save the Tapo account password in the desktop's system keyring—not in this
  project or its configuration file.
- Read locally from the H100; no cloud dashboard or database is required.
- JSON output for scripting and integrations.

The underlying Tapo library documents support for H100 child devices including
KE100, S200B/S200D, S210, T100, T110, T300, T310, and T315. Unknown child
devices are still shown using the raw data returned by the hub.

## Install from a source checkout

Python 3.11 or newer is required (the upstream Tapo client requires 3.11+).

```bash
git clone https://github.com/TWx-Software/tapo-hub-reader.git
cd tapo-hub-reader
python3 -m venv .venv
.venv/bin/python -m pip install .
source .venv/bin/activate
```

On Fedora/KDE, ensure KDE Wallet is running and unlocked. On GNOME, use GNOME
Keyring. The Python `keyring` package uses the desktop's Secret Service
keyring; it does not fall back to storing the password in plaintext.

## First-time setup

Save your account and hub address once:

```bash
tapo-hub auth setup --hub-ip 10.1.1.190
```

The command prompts for your Tapo account email and password. The password is
stored in the OS keyring. The config file under
`~/.config/tapo-hub-reader/` contains only your account name and hub IP.

Check or remove the saved credentials:

```bash
tapo-hub auth status
tapo-hub auth logout
```

## Usage

```bash
tapo-hub                 # Full data for all child devices
tapo-hub --list          # Names, models, and IDs
tapo-hub -t              # Temperature readings
tapo-hub -h              # Humidity readings
tapo-hub -t --short      # Numbers only, one per sensor
tapo-hub -h --short      # Numbers only, one per sensor
tapo-hub --json          # Full data as JSON
tapo-hub --help          # Help (use -h for humidity)
tapo-hub --interval 60   # Refresh every 60 seconds
tapo-hub gui              # Open the local graphical dashboard
```

The dashboard is served only on `127.0.0.1`, opens in your browser, and refreshes
readings every 30 seconds. Use `tapo-hub gui --no-browser` to start the local
server without opening a browser, or `tapo-hub gui --port 8766` to choose a
different local port. Press `Ctrl+C` in the terminal to stop it.

The dashboard can be installed from your browser's install option or menu. The
PWA caches its app shell for offline access, but never caches sensor readings;
live data requires the local server and H100 to be reachable. Since the server
binds only to `127.0.0.1`, it is intentionally not accessible from other devices.

You can override the configured hub address for an individual run:

```bash
tapo-hub --hub-ip 10.1.1.190 --list
```

The computer running the command must be able to reach the H100 on the local
network. The T310 itself communicates with the H100 and does not need its own
Wi-Fi address.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m compileall -q src
```

## License

MIT. See [LICENSE](LICENSE).
