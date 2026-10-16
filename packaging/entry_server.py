"""PyInstaller entry point for the MultiRegistrator server."""

from multiregistrator.server.app import main

if __name__ == "__main__":
    raise SystemExit(main())
