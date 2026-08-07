"""Create the dedicated RAGFlow API token used by the internal portal.

Run this script inside the RAGFlow container. The output file is mounted to the
Mac host and is intentionally written with owner-only permissions.
"""

from __future__ import annotations

import argparse
import os
import secrets
import stat
from datetime import datetime

from api.db.db_models import APIToken
from api.db.services.api_service import APITokenService
from api.utils.api_utils import generate_confirmation_token
from common import settings
from common.time_utils import current_timestamp, datetime_format

from ragflow_env import get_target_tenant_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/ragflow/internal-secrets/internal-portal.env")
    args = parser.parse_args()

    settings.init_settings()
    tenant_id = get_target_tenant_id()
    existing = APITokenService.query(tenant_id=tenant_id, beta="internal-portal")
    if existing:
        token = existing[0].token
    else:
        token = generate_confirmation_token()
        APITokenService.save(
            tenant_id=tenant_id,
            token=token,
            source="agent",
            beta="internal-portal",
            create_time=current_timestamp(),
            create_date=datetime_format(datetime.now()),
            update_time=None,
            update_date=None,
        )

    session_secret = secrets.token_urlsafe(48)
    os.makedirs(os.path.dirname(args.output), mode=0o700, exist_ok=True)
    os.chmod(os.path.dirname(args.output), stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    with open(args.output, "w", encoding="utf-8") as output:
        os.chmod(args.output, stat.S_IRUSR | stat.S_IWUSR)
        output.write("# Generated for the LeTouch internal portal. Do not commit.\n")
        output.write(f"RAGFLOW_API_TOKEN={token}\n")
        output.write(f"SESSION_SECRET={session_secret}\n")
    os.chmod(args.output, stat.S_IRUSR | stat.S_IWUSR)
    print(f"internal portal token ready: {args.output}")


if __name__ == "__main__":
    main()
