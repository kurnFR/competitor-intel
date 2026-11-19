"""Field observations and historical own price snapshots."""

from alembic import op

revision = "j9_field_intelligence"
down_revision = "i8d9e0f1a234"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE competitor_intel.promotions ALTER COLUMN ai_confidence DROP NOT NULL")
    op.execute("""CREATE TABLE competitor_intel.marketing_actions (
        id uuid PRIMARY KEY, promotion_id uuid NOT NULL REFERENCES competitor_intel.promotions(id),
        action text NOT NULL, owner text NOT NULL, due date NOT NULL, status text NOT NULL,
        recorded_by uuid NOT NULL, recorded_at timestamptz NOT NULL DEFAULT now())""")
    op.execute("""
    CREATE TABLE competitor_intel.field_submissions (
        id uuid PRIMARY KEY, submitted_by uuid NOT NULL, submitted_at timestamptz NOT NULL DEFAULT now(),
        payload jsonb NOT NULL, status text NOT NULL DEFAULT 'PENDING',
        reviewed_by uuid, reviewed_at timestamptz, promotion_id uuid REFERENCES competitor_intel.promotions(id)
    )""")
    op.execute("""
    CREATE TABLE competitor_intel.own_price_history (
        revision bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, product_id uuid NOT NULL,
        recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(), operation text NOT NULL, snapshot jsonb NOT NULL
    )""")
    op.execute("CREATE INDEX own_history_product ON competitor_intel.own_price_history(product_id, revision DESC)")
    op.execute("""INSERT INTO competitor_intel.own_price_history(product_id, operation, snapshot)
                  SELECT id, 'BASELINE', to_jsonb(p) FROM competitor_intel.own_products p""")
    op.execute("""
    CREATE FUNCTION competitor_intel.record_own_price() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN
        INSERT INTO competitor_intel.own_price_history(product_id,operation,snapshot) VALUES (OLD.id,TG_OP,to_jsonb(OLD));
      ELSE
        INSERT INTO competitor_intel.own_price_history(product_id,operation,snapshot) VALUES (NEW.id,TG_OP,to_jsonb(NEW));
      END IF;
      RETURN NULL;
    END $$""")
    op.execute("""CREATE TRIGGER own_price_revision AFTER INSERT OR UPDATE OR DELETE ON competitor_intel.own_products
                  FOR EACH ROW EXECUTE FUNCTION competitor_intel.record_own_price()""")


def downgrade():
    op.execute("DROP TABLE competitor_intel.marketing_actions")
    op.execute("UPDATE competitor_intel.promotions SET ai_confidence=0 WHERE ai_confidence IS NULL")
    op.execute("ALTER TABLE competitor_intel.promotions ALTER COLUMN ai_confidence SET NOT NULL")
    op.execute("DROP TRIGGER own_price_revision ON competitor_intel.own_products")
    op.execute("DROP FUNCTION competitor_intel.record_own_price()")
    op.execute("DROP TABLE competitor_intel.own_price_history, competitor_intel.field_submissions")
