"""Initial migration: users, oauth_accounts, sessions, refresh_tokens,
activity_logs, admin_audit, login_history, user_tags, admin_notes, invitations.

Single migration creates all tables to simplify bootstrapping.
"""

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


def upgrade() -> None:
    # ----- users -----
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.Text),
        sa.Column("email", sa.String(320)),
        sa.Column("bio", sa.Text),
        sa.Column("locale", sa.String(10)),
        sa.Column("timezone", sa.String(50)),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("ban_reason", sa.Text),
        sa.Column("last_ip", sa.String(45)),
        sa.Column("last_country", sa.String(100)),
        sa.Column("last_city", sa.String(100)),
        sa.Column("totp_secret", sa.Text),
        sa.Column("totp_enabled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("login_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_users_email", "users", ["email"], unique=False)
    op.create_index("idx_users_status", "users", ["status"])
    op.create_index("idx_users_role", "users", ["role"])
    op.create_index("idx_users_created_at", "users", ["created_at"])

    # ----- oauth_accounts -----
    op.create_table(
        "oauth_accounts",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("provider_email", sa.String(320)),
        sa.Column("provider_name", sa.String(255)),
        sa.Column("provider_avatar", sa.Text),
        sa.Column("access_token", sa.Text),
        sa.Column("refresh_token", sa.Text),
        sa.Column("token_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_uid"),
    )
    op.create_index("idx_oauth_user_id", "oauth_accounts", ["user_id"])
    op.create_index("idx_oauth_provider", "oauth_accounts", ["provider"])

    # ----- sessions -----
    op.create_table(
        "sessions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jti", sa.String(64), nullable=False, unique=True),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_jti", "sessions", ["jti"])
    op.create_index("idx_sessions_expires_at", "sessions", ["expires_at"])

    # ----- refresh_tokens -----
    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_refresh_session_id", "refresh_tokens", ["session_id"])
    op.create_index("idx_refresh_token_hash", "refresh_tokens", ["token_hash"])

    # ----- activity_logs -----
    op.create_table(
        "activity_logs",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("path", sa.Text),
        sa.Column("method", sa.String(10)),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_activity_user_id", "activity_logs", ["user_id"])
    op.create_index("idx_activity_event_type", "activity_logs", ["event_type"])
    op.create_index("idx_activity_created_at", "activity_logs", ["created_at"])

    # ----- admin_audit -----
    op.create_table(
        "admin_audit",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("admin_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_audit_admin_id", "admin_audit", ["admin_user_id"])
    op.create_index("idx_audit_action", "admin_audit", ["action"])
    op.create_index("idx_audit_created_at", "admin_audit", ["created_at"])

    # ----- login_history -----
    op.create_table(
        "login_history",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("country", sa.String(100)),
        sa.Column("city", sa.String(100)),
        sa.Column("user_agent", sa.Text),
        sa.Column("device_type", sa.String(20)),
        sa.Column("os", sa.String(50)),
        sa.Column("browser", sa.String(50)),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("failure_reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_login_user_id", "login_history", ["user_id"])
    op.create_index("idx_login_created_at", "login_history", ["created_at"])
    op.create_index("idx_login_ip", "login_history", ["ip_address"])

    # ----- user_tags -----
    op.create_table(
        "user_tags",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("color", sa.String(7)),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ----- user_tag_assignments -----
    op.create_table(
        "user_tag_assignments",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", UUID(as_uuid=True), sa.ForeignKey("user_tags.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("assigned_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # ----- admin_notes -----
    op.create_table(
        "admin_notes",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("admin_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_notes_user_id", "admin_notes", ["user_id"])

    # ----- invitations -----
    op.create_table(
        "invitations",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("used_by", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("max_uses", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("use_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_invitations_code", "invitations", ["code"])


def downgrade() -> None:
    op.drop_table("invitations")
    op.drop_table("admin_notes")
    op.drop_table("user_tag_assignments")
    op.drop_table("user_tags")
    op.drop_table("login_history")
    op.drop_table("admin_audit")
    op.drop_table("activity_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("sessions")
    op.drop_table("oauth_accounts")
    op.drop_table("users")
