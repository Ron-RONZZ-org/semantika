"""Entry point for `python -m semantika`."""

import uvicorn

from semantika.server.app import create_app


def main() -> None:
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=6015)


if __name__ == "__main__":
    main()
