"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-11-12

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("yaml", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_suites"),
    )
    op.create_index("ix_suites_name", "suites", ["name"])

    op.create_table(
        "runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suite_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suite_path", sa.String(length=1024), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("git_ref", sa.String(length=255), nullable=True),
        sa.Column("baseline_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=True),
        sa.Column("wilson_low", sa.Float(), nullable=False),
        sa.Column("wilson_high", sa.Float(), nullable=False),
        sa.Column("total_cases", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("p95_latency_ms", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["suite_id"], ["suites.id"], name="fk_runs_suite_id_suites", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["baseline_run_id"],
            ["runs.id"],
            name="fk_runs_baseline_run_id_runs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_runs"),
    )
    op.create_index("ix_runs_suite_id", "runs", ["suite_id"])
    op.create_index("ix_runs_commit_sha", "runs", ["commit_sha"])
    op.create_index("ix_runs_git_ref", "runs", ["git_ref"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_suite_started", "runs", ["suite_id", "started_at"])

    op.create_table(
        "results",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.String(length=128), nullable=False),
        sa.Column("metric", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("judge_output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name="fk_results_run_id_runs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_results"),
        sa.UniqueConstraint("run_id", "case_id", "metric", name="uq_results_run_case_metric"),
    )
    op.create_index("ix_results_run_id", "results", ["run_id"])

    op.create_table(
        "judge_cache",
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("rubric_hash", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("hash", name="pk_judge_cache"),
    )
    op.create_index("ix_judge_cache_response_hash", "judge_cache", ["response_hash"])
    op.create_index("ix_judge_cache_model", "judge_cache", ["model"])


def downgrade() -> None:
    op.drop_index("ix_judge_cache_model", table_name="judge_cache")
    op.drop_index("ix_judge_cache_response_hash", table_name="judge_cache")
    op.drop_table("judge_cache")
    op.drop_index("ix_results_run_id", table_name="results")
    op.drop_table("results")
    op.drop_index("ix_runs_suite_started", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_git_ref", table_name="runs")
    op.drop_index("ix_runs_commit_sha", table_name="runs")
    op.drop_index("ix_runs_suite_id", table_name="runs")
    op.drop_table("runs")
    op.drop_index("ix_suites_name", table_name="suites")
    op.drop_table("suites")
