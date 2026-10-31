"""Report downloads/shares remain explicit actions without Owner approval."""

from alembic import op

revision = "20261031_0049"
down_revision = "20261031_0048"
branch_labels = None
depends_on = None

AREAS = """'clientCreation','clientDetails','clientLifecycle','assessments',
    'trainerCreation','trainerDetails','trainerAssignment','trainerLifecycle',
    'sessionScheduling','sessionContent','sessionAcknowledgement',
    'packageCatalogue','clientPackages','exerciseLibrary','content'"""


def upgrade():
    # Retain immutable account-change receipts; only the withdrawn policy is retired.
    op.execute("DELETE FROM admin_approval_requirements WHERE area = 'reports'")
    op.drop_constraint(
        op.f("ck_admin_approval_requirements_area_values"), "admin_approval_requirements"
    )
    op.create_check_constraint(
        op.f("ck_admin_approval_requirements_area_values"),
        "admin_approval_requirements",
        f"area IN ({AREAS})",
    )


def downgrade():
    # Widen the accepted vocabulary without inventing prior approval selections.
    op.drop_constraint(
        op.f("ck_admin_approval_requirements_area_values"), "admin_approval_requirements"
    )
    op.create_check_constraint(
        op.f("ck_admin_approval_requirements_area_values"),
        "admin_approval_requirements",
        f"area IN ({AREAS},'reports')",
    )
