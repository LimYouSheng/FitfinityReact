"""Separate sharing approval from always-permitted downloads and uploads."""

from alembic import op

revision = "20261101_0052"
down_revision = "20261031_0051"
branch_labels = None
depends_on = None

AREAS = """'clientCreation','clientDetails','clientLifecycle','assessments',
 'trainerCreation','trainerDetails','trainerAssignment','trainerLifecycle',
 'sessionScheduling','sessionContent','sessionAcknowledgement','packageCatalogue',
 'clientPackages','exerciseLibrary','content'"""


def upgrade():
    # Defaults apply at new account creation; do not rewrite existing Owner selections.
    op.drop_constraint(
        op.f("ck_admin_approval_requirements_area_values"), "admin_approval_requirements"
    )
    op.create_check_constraint(
        op.f("ck_admin_approval_requirements_area_values"),
        "admin_approval_requirements",
        f"area IN ({AREAS},'progressReportSharing','sessionPdfSharing')",
    )


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM admin_approval_requirements
        WHERE area IN ('progressReportSharing','sessionPdfSharing')) THEN
        RAISE EXCEPTION 'Retain sharing approval selections before downgrade';
      END IF;
    END $$""")
    op.drop_constraint(
        op.f("ck_admin_approval_requirements_area_values"), "admin_approval_requirements"
    )
    op.create_check_constraint(
        op.f("ck_admin_approval_requirements_area_values"),
        "admin_approval_requirements",
        f"area IN ({AREAS})",
    )
