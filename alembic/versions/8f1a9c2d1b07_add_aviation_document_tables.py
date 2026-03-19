"""add_aviation_document_tables

Revision ID: 8f1a9c2d1b07
Revises: 3a1b2c3d4e5f
Create Date: 2026-03-19

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f1a9c2d1b07"
down_revision: Union[str, None] = "3a1b2c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aviation_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_key", sa.String(length=256), nullable=False),
        sa.Column("revision_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_latest", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_path", sa.String(length=1024), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("parsed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="low"),
        sa.Column("parse_warnings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("header_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("totals_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("raw_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_aviation_documents_document_key"), "aviation_documents", ["document_key"], unique=False)
    op.create_index(op.f("ix_aviation_documents_is_latest"), "aviation_documents", ["is_latest"], unique=False)
    op.create_index(op.f("ix_aviation_documents_content_sha256"), "aviation_documents", ["content_sha256"], unique=False)

    op.create_table(
        "aviation_document_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("section_type", sa.String(length=64), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("service_interval", sa.String(length=256), nullable=True),
        sa.Column("task_reference", sa.String(length=256), nullable=True),
        sa.Column("ata_chapter", sa.String(length=16), nullable=True),
        sa.Column("ata_derived", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("man_hours", sa.Float(), nullable=True),
        sa.Column("task_type", sa.String(length=32), nullable=True),
        sa.Column("ad_reference", sa.String(length=256), nullable=True),
        sa.Column("component_pn", sa.String(length=256), nullable=True),
        sa.Column("component_sn", sa.String(length=256), nullable=True),
        sa.Column("component_position", sa.String(length=64), nullable=True),
        sa.Column("component_description", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=128), nullable=True),
        sa.Column("raw_line", sa.Text(), nullable=True),
        sa.Column("extra_fields", sa.JSON(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["document_id"], ["aviation_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_aviation_document_tasks_document_id"), "aviation_document_tasks", ["document_id"], unique=False)
    op.create_index(op.f("ix_aviation_document_tasks_section_type"), "aviation_document_tasks", ["section_type"], unique=False)
    op.create_index(op.f("ix_aviation_document_tasks_line_number"), "aviation_document_tasks", ["line_number"], unique=False)
    op.create_index(op.f("ix_aviation_document_tasks_service_interval"), "aviation_document_tasks", ["service_interval"], unique=False)
    op.create_index(op.f("ix_aviation_document_tasks_task_reference"), "aviation_document_tasks", ["task_reference"], unique=False)
    op.create_index(op.f("ix_aviation_document_tasks_ata_chapter"), "aviation_document_tasks", ["ata_chapter"], unique=False)
    op.create_index(op.f("ix_aviation_document_tasks_task_type"), "aviation_document_tasks", ["task_type"], unique=False)

    op.create_table(
        "aviation_document_parts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("task_reference", sa.String(length=256), nullable=True),
        sa.Column("part_number", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("part_type", sa.String(length=64), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("raw_line", sa.Text(), nullable=True),
        sa.Column("extra_fields", sa.JSON(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["document_id"], ["aviation_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_aviation_document_parts_document_id"), "aviation_document_parts", ["document_id"], unique=False)
    op.create_index(op.f("ix_aviation_document_parts_task_reference"), "aviation_document_parts", ["task_reference"], unique=False)
    op.create_index(op.f("ix_aviation_document_parts_part_number"), "aviation_document_parts", ["part_number"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_aviation_document_parts_part_number"), table_name="aviation_document_parts")
    op.drop_index(op.f("ix_aviation_document_parts_task_reference"), table_name="aviation_document_parts")
    op.drop_index(op.f("ix_aviation_document_parts_document_id"), table_name="aviation_document_parts")
    op.drop_table("aviation_document_parts")

    op.drop_index(op.f("ix_aviation_document_tasks_task_type"), table_name="aviation_document_tasks")
    op.drop_index(op.f("ix_aviation_document_tasks_ata_chapter"), table_name="aviation_document_tasks")
    op.drop_index(op.f("ix_aviation_document_tasks_task_reference"), table_name="aviation_document_tasks")
    op.drop_index(op.f("ix_aviation_document_tasks_service_interval"), table_name="aviation_document_tasks")
    op.drop_index(op.f("ix_aviation_document_tasks_line_number"), table_name="aviation_document_tasks")
    op.drop_index(op.f("ix_aviation_document_tasks_section_type"), table_name="aviation_document_tasks")
    op.drop_index(op.f("ix_aviation_document_tasks_document_id"), table_name="aviation_document_tasks")
    op.drop_table("aviation_document_tasks")

    op.drop_index(op.f("ix_aviation_documents_content_sha256"), table_name="aviation_documents")
    op.drop_index(op.f("ix_aviation_documents_is_latest"), table_name="aviation_documents")
    op.drop_index(op.f("ix_aviation_documents_document_key"), table_name="aviation_documents")
    op.drop_table("aviation_documents")

