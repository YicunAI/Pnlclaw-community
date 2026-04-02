"""Pro storage repositories — async data-access layer for all Pro tables.

Usage::

    from pnlclaw_pro_storage.repositories import UserRepository

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
"""

from pnlclaw_pro_storage.repositories.activity import ActivityLogRepository
from pnlclaw_pro_storage.repositories.admin_audit import AdminAuditRepository
from pnlclaw_pro_storage.repositories.admin_notes import AdminNoteRepository
from pnlclaw_pro_storage.repositories.invitations import InvitationRepository
from pnlclaw_pro_storage.repositories.login_history import LoginHistoryRepository
from pnlclaw_pro_storage.repositories.oauth_accounts import OAuthAccountRepository
from pnlclaw_pro_storage.repositories.sessions import SessionRepository
from pnlclaw_pro_storage.repositories.user_tags import UserTagRepository
from pnlclaw_pro_storage.repositories.users import UserRepository

__all__ = [
    "ActivityLogRepository",
    "AdminAuditRepository",
    "AdminNoteRepository",
    "InvitationRepository",
    "LoginHistoryRepository",
    "OAuthAccountRepository",
    "SessionRepository",
    "UserRepository",
    "UserTagRepository",
]
