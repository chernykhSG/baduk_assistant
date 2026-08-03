import json
import sys


def main() -> None:
    # Simulate KataGo's verbose startup logging: write enough to stderr to
    # exceed the OS pipe buffer (typically 64KB or less) before the process
    # ever reads stdin. If the parent doesn't drain stderr concurrently, this
    # write blocks forever and the parent's analyze() call hangs until its
    # timeout expires instead of returning promptly.
    for i in range(3000):
        print(f"startup log line {i} " + "x" * 100, file=sys.stderr)
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        print(f"handling request {request['id']}", file=sys.stderr)
        response = {"id": request["id"], "ok": True}
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
