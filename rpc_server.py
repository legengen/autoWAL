#!/usr/bin/env python3
import argparse

from autowal.rpc import serve


def main():
    parser = argparse.ArgumentParser(description="autoWAL XML-RPC server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.host, args.port)


if __name__ == "__main__":
    main()
