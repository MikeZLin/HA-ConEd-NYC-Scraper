from __future__ import annotations


def main() -> None:
    try:
        import uvicorn
    except ImportError as error:
        raise SystemExit("Install coned-scraper[api] to run the service") from error
    uvicorn.run("coned_scraper.api:create_app", factory=True, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
