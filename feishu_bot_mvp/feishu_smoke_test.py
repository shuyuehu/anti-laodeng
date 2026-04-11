#!/usr/bin/env python3
import json
import os
import sys
import urllib.request


TENANT_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"


def post_json(url: str, payload: dict) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("Missing FEISHU_APP_ID or FEISHU_APP_SECRET", file=sys.stderr)
        return 1

    response = post_json(
        TENANT_TOKEN_URL,
        {"app_id": app_id, "app_secret": app_secret},
    )
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("code") == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
