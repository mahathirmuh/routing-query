"""
queries.py — Query Generators for 3 Complexity Levels

Generates parameterized queries for benchmarking:
  - Simple:  Single-table PK lookup (SELECT * FROM orders WHERE id = $1)
  - Medium:  JOIN 2 tables with filter
  - Complex: JOIN 3 tables with GROUP BY + aggregation
"""

import random
from dataclasses import dataclass


@dataclass
class QueryTemplate:
    """A parameterized query with its complexity level."""
    sql: str
    params_fn: callable  # Function that returns a tuple of parameters
    complexity: str       # 'simple', 'medium', 'complex'
    query_type: str       # 'read' or 'write'


# =============================================================================
# Constants for parameter generation
# =============================================================================
MAX_ORDER_ID = 500_000
MAX_CUSTOMER_ID = 10_000
MAX_PRODUCT_ID = 1_000
REGIONS = ["Asia", "Europe", "Americas", "Africa", "Oceania"]
STATUSES = ["pending", "processing", "shipped", "delivered", "cancelled"]
TIERS = ["Bronze", "Silver", "Gold", "Platinum"]
CATEGORIES = [
    "Electronics", "Clothing", "Food", "Books", "Sports",
    "Home", "Toys", "Health", "Auto", "Garden"
]


# =============================================================================
# READ Queries — 3 Complexity Levels
# =============================================================================

def simple_read_queries(rng: random.Random) -> list[QueryTemplate]:
    """Simple: Single-table PK lookup."""
    return [
        QueryTemplate(
            sql="SELECT id, customer_id, product_id, quantity, total_price, status, region, order_date FROM orders WHERE id = $1",
            params_fn=lambda: (rng.randint(1, MAX_ORDER_ID),),
            complexity="simple",
            query_type="read",
        ),
        QueryTemplate(
            sql="SELECT id, name, email, region, tier FROM customers WHERE id = $1",
            params_fn=lambda: (rng.randint(1, MAX_CUSTOMER_ID),),
            complexity="simple",
            query_type="read",
        ),
        QueryTemplate(
            sql="SELECT id, name, category, price, stock FROM products WHERE id = $1",
            params_fn=lambda: (rng.randint(1, MAX_PRODUCT_ID),),
            complexity="simple",
            query_type="read",
        ),
    ]


def medium_read_queries(rng: random.Random) -> list[QueryTemplate]:
    """Medium: JOIN 2 tables with filter."""
    return [
        QueryTemplate(
            sql=(
                "SELECT o.id, o.total_price, o.status, o.order_date, c.name, c.tier "
                "FROM orders o "
                "JOIN customers c ON o.customer_id = c.id "
                "WHERE o.region = $1 "
                "LIMIT 50"
            ),
            params_fn=lambda: (rng.choice(REGIONS),),
            complexity="medium",
            query_type="read",
        ),
        QueryTemplate(
            sql=(
                "SELECT o.id, o.quantity, o.total_price, p.name AS product_name, p.category "
                "FROM orders o "
                "JOIN products p ON o.product_id = p.id "
                "WHERE o.status = $1 "
                "LIMIT 50"
            ),
            params_fn=lambda: (rng.choice(STATUSES),),
            complexity="medium",
            query_type="read",
        ),
        QueryTemplate(
            sql=(
                "SELECT c.id, c.name, c.email, c.tier, COUNT(o.id) AS order_count "
                "FROM customers c "
                "JOIN orders o ON c.id = o.customer_id "
                "WHERE c.region = $1 "
                "GROUP BY c.id, c.name, c.email, c.tier "
                "LIMIT 20"
            ),
            params_fn=lambda: (rng.choice(REGIONS),),
            complexity="medium",
            query_type="read",
        ),
    ]


def complex_read_queries(rng: random.Random) -> list[QueryTemplate]:
    """Complex: JOIN 3 tables with GROUP BY + aggregation."""
    return [
        QueryTemplate(
            sql=(
                "SELECT c.region, p.category, "
                "COUNT(*) AS order_count, "
                "AVG(o.total_price) AS avg_price, "
                "SUM(o.quantity) AS total_qty "
                "FROM orders o "
                "JOIN customers c ON o.customer_id = c.id "
                "JOIN products p ON o.product_id = p.id "
                "WHERE o.region = $1 "
                "GROUP BY c.region, p.category "
                "ORDER BY order_count DESC "
                "LIMIT 10"
            ),
            params_fn=lambda: (rng.choice(REGIONS),),
            complexity="complex",
            query_type="read",
        ),
        QueryTemplate(
            sql=(
                "SELECT c.tier, p.category, "
                "COUNT(DISTINCT o.customer_id) AS unique_customers, "
                "COUNT(*) AS total_orders, "
                "AVG(o.total_price) AS avg_price, "
                "MAX(o.total_price) AS max_price "
                "FROM orders o "
                "JOIN customers c ON o.customer_id = c.id "
                "JOIN products p ON o.product_id = p.id "
                "WHERE o.status = $1 "
                "GROUP BY c.tier, p.category "
                "ORDER BY total_orders DESC "
                "LIMIT 20"
            ),
            params_fn=lambda: (rng.choice(STATUSES),),
            complexity="complex",
            query_type="read",
        ),
        QueryTemplate(
            sql=(
                "SELECT DATE_TRUNC('month', o.order_date) AS month, "
                "c.region, "
                "COUNT(*) AS order_count, "
                "SUM(o.total_price) AS revenue, "
                "AVG(o.quantity) AS avg_qty "
                "FROM orders o "
                "JOIN customers c ON o.customer_id = c.id "
                "JOIN products p ON o.product_id = p.id "
                "WHERE p.category = $1 "
                "GROUP BY month, c.region "
                "ORDER BY month DESC, revenue DESC "
                "LIMIT 15"
            ),
            params_fn=lambda: (rng.choice(CATEGORIES),),
            complexity="complex",
            query_type="read",
        ),
    ]


# =============================================================================
# WRITE Queries
# =============================================================================

def write_queries(rng: random.Random) -> list[QueryTemplate]:
    """Write queries: INSERT and UPDATE on orders."""
    import datetime

    return [
        QueryTemplate(
            sql=(
                "INSERT INTO orders "
                "(customer_id, product_id, quantity, total_price, status, region, order_date) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                "RETURNING id"
            ),
            params_fn=lambda: (
                rng.randint(1, MAX_CUSTOMER_ID),
                rng.randint(1, MAX_PRODUCT_ID),
                rng.randint(1, 10),
                round(rng.uniform(1, 5000), 2),
                rng.choice(STATUSES),
                rng.choice(REGIONS),
                datetime.date(2026, rng.randint(1, 12), rng.randint(1, 28)),
            ),
            complexity="simple",
            query_type="write",
        ),
        QueryTemplate(
            sql=(
                "UPDATE orders SET status = $1, total_price = $2 "
                "WHERE id = $3"
            ),
            params_fn=lambda: (
                rng.choice(STATUSES),
                round(rng.uniform(1, 5000), 2),
                rng.randint(1, MAX_ORDER_ID),
            ),
            complexity="simple",
            query_type="write",
        ),
    ]


# =============================================================================
# Query pool factory
# =============================================================================

def get_query_pool(
    complexity: str,
    seed: int = 42
) -> tuple[list[QueryTemplate], list[QueryTemplate]]:
    """
    Get read and write query pools for a given complexity level.

    Returns: (read_queries, write_queries)
    """
    rng = random.Random(seed)

    if complexity == "simple":
        reads = simple_read_queries(rng)
    elif complexity == "medium":
        reads = medium_read_queries(rng)
    elif complexity == "complex":
        reads = complex_read_queries(rng)
    else:
        raise ValueError(f"Unknown complexity: {complexity}. Use: simple, medium, complex")

    writes = write_queries(rng)
    return reads, writes
