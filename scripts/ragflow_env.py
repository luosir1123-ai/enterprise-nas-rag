"""Helpers for RAGFlow scripts that run inside the RAGFlow container."""

from __future__ import annotations

import os

from common.constants import StatusEnum
from api.db import db_models


DEFAULT_TENANT_EMAIL = "3307608589@qq.com"


def get_target_user_email() -> str:
    return os.getenv("RAGFLOW_TENANT_EMAIL", DEFAULT_TENANT_EMAIL)


def get_target_tenant_id() -> str:
    """Return the active tenant ID for the configured user email.

    The Mac mini RAGFlow instance was re-created, so fixed tenant IDs from the
    earlier Ubuntu environment are no longer valid. Prefer an explicit
    RAGFLOW_TENANT_ID, otherwise resolve from RAGFLOW_TENANT_EMAIL.
    """
    explicit = os.getenv("RAGFLOW_TENANT_ID", "").strip()
    if explicit:
        return explicit

    email = get_target_user_email()
    user = db_models.User.get_or_none(
        (db_models.User.email == email)
        & (db_models.User.status == StatusEnum.VALID.value)
    )
    if not user:
        raise RuntimeError(f"active RAGFlow user not found: {email}")

    owner_link = db_models.UserTenant.get_or_none(
        (db_models.UserTenant.user_id == user.id)
        & (db_models.UserTenant.role == "owner")
        & (db_models.UserTenant.status == StatusEnum.VALID.value)
    )
    if owner_link:
        return owner_link.tenant_id

    link = db_models.UserTenant.get_or_none(
        (db_models.UserTenant.user_id == user.id)
        & (db_models.UserTenant.status == StatusEnum.VALID.value)
    )
    if not link:
        raise RuntimeError(f"tenant link not found for user: {email}")
    return link.tenant_id


def get_target_tenant():
    tenant_id = get_target_tenant_id()
    tenant = db_models.Tenant.get_or_none(
        (db_models.Tenant.id == tenant_id)
        & (db_models.Tenant.status == StatusEnum.VALID.value)
    )
    if not tenant:
        raise RuntimeError(f"active RAGFlow tenant not found: {tenant_id}")
    return tenant
