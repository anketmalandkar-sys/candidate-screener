"""Initial schema

Revision ID: 0001
Revises:

The whole schema in one migration — recruiters, roles and their requirements,
and the candidate pool.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_roles_user_id", "roles", ["user_id"])

    op.create_table(
        "requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "role_id",
            sa.Integer(),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "aliases",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "weight BETWEEN 1 AND 3", name="ck_requirement_weight_range"
        ),
    )
    op.create_index("ix_requirements_role_id", "requirements", ["role_id"])

    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("resume_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False, server_default="paste"),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_candidates_user_id", "candidates", ["user_id"])


def downgrade() -> None:
    op.drop_table("candidates")
    op.drop_table("requirements")
    op.drop_table("roles")
    op.drop_table("users")
