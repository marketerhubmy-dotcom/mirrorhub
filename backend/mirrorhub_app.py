"""PyInstaller entry point."""
import multiprocessing
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from desktop import main
    sys.exit(main())
