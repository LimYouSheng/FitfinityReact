"""Allow independently owned purchases to overlap; booking conflicts remain enforced."""

import sqlalchemy as sa
from alembic import op

revision = "20261031_0047"
down_revision = "20261025_0046"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE package_purchases DROP CONSTRAINT ex_purchase_dates")


def downgrade():
    overlaps = op.get_bind().scalar(
        sa.text("""
        SELECT EXISTS (
            SELECT 1 FROM package_purchases a JOIN package_purchases b
            ON a.client_id = b.client_id AND a.id < b.id
            WHERE a.status = 'active' AND b.status = 'active'
            AND daterange(a.start_date, a.end_date, '[]') &&
                daterange(b.start_date, b.end_date, '[]')
        )
    """)
    )
    if overlaps:
        raise RuntimeError("Concurrent purchase evidence requires compatible application code")
    op.execute("""ALTER TABLE package_purchases ADD CONSTRAINT ex_purchase_dates
        EXCLUDE USING gist (client_id WITH =,
        daterange(start_date, end_date, '[]') WITH &&) WHERE (status = 'active')""")
