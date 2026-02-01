# Installation

This guide covers how to install the `alpha-hwr` library and its dependencies.

## Prerequisites

*   Python 3.13 or higher.
*   A supported Bluetooth Low Energy (BLE) adapter (internal or USB dongle).
*   **Operating System**:
    *   **Linux**: Recommended for full feature support (especially Schedule downloading).
    *   **macOS**: Supported for Control and Telemetry (Schedule download is currently restricted by the OS).
    *   **Windows**: Supported for Control and Telemetry.

## Installing via pip

*Note: The package is not yet on PyPI. Installation is currently from source.*

```bash
# Future command
pip install alpha-hwr
```

## Installing from Source

To use the latest development version or contribute to the project:

1.  Clone the repository:
    ```bash
    git clone https://github.com/eman/alpha-hwr.git
    cd alpha-hwr
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

    *If `requirements.txt` is not present, install the core dependencies:*
    ```bash
    pip install bleak pydantic rich typer
    ```

4.  **Install the package in editable mode:**
    ```bash
    pip install -e .
    ```

## Platform-Specific Notes

### Linux (Raspberry Pi / Debian / Ubuntu)

Bleak (the underlying BLE library) uses BlueZ on Linux. You might need to install development headers:

```bash
sudo apt-get install libglib2.0-dev libbluetooth-dev python3-dev
```

**Permissions:**
By default, accessing the Bluetooth adapter requires `root` privileges. To run scripts without `sudo`, you can grant the Python interpreter the necessary capabilities:

```bash
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python3))
```
*(Note: This applies to the specific python binary found in your path. If using a venv, apply it to the venv's python binary).*

### macOS

On macOS, you must grant **Bluetooth Permission** to your terminal application (e.g., iTerm2, Terminal.app, VS Code) in `System Settings -> Privacy & Security -> Bluetooth`.

The first time you run a script, macOS usually prompts you to allow access.