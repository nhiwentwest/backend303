"""
Initial schema from legacy SQL (imported from init-db/01_init.sql)
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '0001_init_schema_from_legacy_sql'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    with open('init-db/01_init.sql', 'r') as f:
        sql = f.read()
    op.execute(sql)

def downgrade():
    # Xóa các bảng theo thứ tự phụ thuộc ngược lại
    op.execute('''
    DROP TABLE IF EXISTS compressed_data_optimized CASCADE;
    DROP TABLE IF EXISTS original_samples CASCADE;
    DROP TABLE IF EXISTS sensor_data CASCADE;
    DROP TABLE IF EXISTS feeds CASCADE;
    DROP TABLE IF EXISTS devices CASCADE;
    DROP TABLE IF EXISTS users CASCADE;
    ''') 