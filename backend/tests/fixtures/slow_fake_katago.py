import json
import sys
import time


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        time.sleep(0.3)
        response = {
            "id": request["id"],
            "turnNumber": 0,
            "moveInfos": [
                {
                    "move": "Q4",
                    "winrate": 0.55,
                    "scoreLead": 1.2,
                    "visits": 50,
                    "prior": 0.3,
                    "pv": ["Q4", "D4"],
                }
            ],
            "rootInfo": {"winrate": 0.55, "scoreLead": 1.2, "visits": 50},
            "ownership": [0.1] * 361,
        }
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
