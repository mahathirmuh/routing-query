-- =============================================================================
-- PostgreSQL Benchmark Database — Schema + Seed Data (500K rows)
-- =============================================================================

-- =====================
-- 1. Schema Definition
-- =====================

-- Customers table (10,000 rows)
CREATE TABLE IF NOT EXISTS customers (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(150) NOT NULL,
    region      VARCHAR(50) NOT NULL,
    tier        VARCHAR(20) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Products table (1,000 rows)
CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(150) NOT NULL,
    category    VARCHAR(50) NOT NULL,
    price       NUMERIC(10,2) NOT NULL,
    stock       INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Orders table (500,000 rows) — main benchmark table
CREATE TABLE IF NOT EXISTS orders (
    id           SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    product_id   INTEGER NOT NULL REFERENCES products(id),
    quantity     INTEGER NOT NULL,
    total_price  NUMERIC(12,2) NOT NULL,
    status       VARCHAR(20) NOT NULL,
    region       VARCHAR(50) NOT NULL,
    order_date   DATE NOT NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

-- =====================
-- 2. Seed Customers (10K)
-- =====================
INSERT INTO customers (name, email, region, tier)
SELECT
    'Customer_' || gs.id,
    'customer' || gs.id || '@example.com',
    (ARRAY['Asia', 'Europe', 'Americas', 'Africa', 'Oceania'])[1 + (gs.id % 5)],
    (ARRAY['Bronze', 'Silver', 'Gold', 'Platinum'])[1 + (gs.id % 4)]
FROM generate_series(1, 10000) AS gs(id);

-- =====================
-- 3. Seed Products (1K)
-- =====================
INSERT INTO products (name, category, price, stock)
SELECT
    'Product_' || gs.id,
    (ARRAY['Electronics', 'Clothing', 'Food', 'Books', 'Sports',
           'Home', 'Toys', 'Health', 'Auto', 'Garden'])[1 + (gs.id % 10)],
    ROUND((RANDOM() * 999 + 1)::numeric, 2),
    (RANDOM() * 1000)::integer
FROM generate_series(1, 1000) AS gs(id);

-- =====================
-- 4. Seed Orders (500K)
-- =====================
-- Use a deterministic seed via setseed for reproducibility
SELECT setseed(0.42);

INSERT INTO orders (customer_id, product_id, quantity, total_price, status, region, order_date)
SELECT
    1 + (gs.id % 10000),                                                      -- customer_id (1-10000)
    1 + (gs.id % 1000),                                                       -- product_id (1-1000)
    1 + (gs.id % 10),                                                         -- quantity (1-10)
    ROUND((RANDOM() * 4999 + 1)::numeric, 2),                                 -- total_price
    (ARRAY['pending','processing','shipped','delivered','cancelled'])[1 + (gs.id % 5)],  -- status
    (ARRAY['Asia','Europe','Americas','Africa','Oceania'])[1 + (gs.id % 5)],   -- region
    DATE '2023-01-01' + (gs.id % 730)                                          -- order_date (2 years range)
FROM generate_series(1, 500000) AS gs(id);

-- =====================
-- 5. Create Indexes
-- =====================

-- Primary key lookups (already via PK)
-- For JOIN + filter queries
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_product_id ON orders(product_id);
CREATE INDEX idx_orders_region ON orders(region);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_order_date ON orders(order_date);
CREATE INDEX idx_orders_region_status ON orders(region, status);
CREATE INDEX idx_customers_region ON customers(region);
CREATE INDEX idx_customers_tier ON customers(tier);
CREATE INDEX idx_products_category ON products(category);

-- =====================
-- 6. Analyze tables for query planner
-- =====================
ANALYZE customers;
ANALYZE products;
ANALYZE orders;

-- =====================
-- 7. Verify seed data
-- =====================
DO $$
DECLARE
    v_customers INTEGER;
    v_products INTEGER;
    v_orders INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_customers FROM customers;
    SELECT COUNT(*) INTO v_products FROM products;
    SELECT COUNT(*) INTO v_orders FROM orders;

    RAISE NOTICE '=== Seed Data Verification ===';
    RAISE NOTICE 'Customers: % rows', v_customers;
    RAISE NOTICE 'Products: % rows', v_products;
    RAISE NOTICE 'Orders: % rows', v_orders;

    IF v_orders < 500000 THEN
        RAISE EXCEPTION 'Expected 500000 orders, got %', v_orders;
    END IF;
END $$;
