def main() -> None:
    import sys

    # If CLI subcommand given, use CLI; otherwise open GUI.
    if len(sys.argv) > 1 and sys.argv[1] in {
        "make",
        "status",
        "connect-tiktok",
        "-h",
        "--help",
    }:
        from clipmaker.cli import main as cli_main

        raise SystemExit(cli_main())

    from clipmaker.app import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
