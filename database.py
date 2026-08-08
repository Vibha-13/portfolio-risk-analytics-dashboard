"""
database.py
-----------
This file owns ALL direct SQL interaction for the project.

WHY THIS FILE EXISTS AS A SEPARATE MODULE:
Interviewers often ask "why did you separate your database code from your
business logic?" The answer: separation of concerns. If we ever needed to
switch from SQLite to PostgreSQL (a real possibility at a company like LSEG,
which uses enterprise-grade relational databases), we would only need to
change THIS file. portfolio.py, analytics.py, and dashboard.py never talk to
SQL directly -- they call functions defined here. This is a basic but real
software engineering principle: isolate the thing most likely to change.

We deliberately use the raw `sqlite3` module instead of an ORM (like
SQLAlchemy). This is intentional for interview purposes -- it forces us to
write and understand real SQL, which is exactly what LSEG's JD asks for
("Exposure to relational databases"). An ORM would hide that SQL from us.
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "portfolio.db")


def get_connection():
    """
    Returns a new SQLite connection.

    WHY a function instead of one global connection object:
    SQLite connections are not guaranteed thread-safe by default, and
    Streamlit re-runs your script on every user interaction. Opening a
    fresh, short-lived connection per operation avoids subtle bugs from
    a stale or shared connection across reruns. This is a real tradeoff
    worth mentioning in an interview -- "I chose correctness and simplicity
    over the small performance cost of reopening connections."
    """
    conn = sqlite3.connect(DB_PATH)
    # Enforce foreign key constraints -- OFF by default in SQLite, which
    # surprises a lot of people. Without this line, deleting a portfolio
    # would silently leave orphaned holdings/transactions behind.
    conn.execute("PRAGMA foreign_keys = ON")
    # Lets us access columns by name (row["symbol"]) instead of only by
    # index (row[2]) -- makes every other file far more readable.
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Creates all four tables if they don't already exist, using a normalized
    schema (3NF-ish, appropriate for a project this size).

    SCHEMA DESIGN REASONING (a very likely interview question):

    users
        id, name, email, created_at
        -- Root entity. Everything else eventually traces back to a user.

    portfolios
        id, user_id (FK -> users), name, created_at
        -- A user can own multiple portfolios (e.g. "Retirement", "Trading").
        -- One-to-many: one user -> many portfolios.

    holdings
        id, portfolio_id (FK -> portfolios), symbol, quantity,
        avg_buy_price, sector, last_updated
        -- Represents CURRENT state: "this portfolio currently holds X
        -- shares of AAPL at an average buy price of Y." This is a
        -- derived/summary table -- it's a cache of the *result* of all
        -- BUY/SELL transactions for that symbol, so we don't have to
        -- recompute it from the full transaction history every time we
        -- want to just show current holdings. Classic tradeoff:
        -- redundancy for read-speed, kept consistent by updating it
        -- every time a transaction happens.

    transactions
        id, portfolio_id (FK -> portfolios), symbol, type (BUY/SELL),
        quantity, price, transaction_date
        -- The full, immutable history/audit log. Financial systems care
        -- a lot about audit trails -- you never delete or edit a past
        -- transaction, you only ever add new ones. This is why
        -- "holdings" and "transactions" are BOTH needed: transactions is
        -- the source of truth (append-only ledger), holdings is a fast
        -- derived snapshot.

    This holdings-vs-transactions split is a genuinely good thing to explain
    confidently -- it mirrors how real accounting/ledger systems work.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            quantity REAL NOT NULL,
            avg_buy_price REAL NOT NULL,
            sector TEXT,
            last_updated TEXT NOT NULL,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE,
            UNIQUE(portfolio_id, symbol)
        )
    """)
    # UNIQUE(portfolio_id, symbol) means: a single portfolio can only have
    # ONE row for a given stock symbol. If you buy more AAPL, we UPDATE
    # that existing row (recalculate avg_buy_price) rather than inserting
    # a duplicate. This is a real constraint decision worth explaining.

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('BUY', 'SELL')),
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            transaction_date TEXT NOT NULL,
            FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
        )
    """)
    # CHECK(type IN ('BUY','SELL')) -- a database-level guardrail. Even if
    # a bug in our Python code tried to insert type='BUYY', SQLite itself
    # would reject it. Good to mention: validation belongs at multiple
    # layers, not just in the application code.

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# USER OPERATIONS
# ---------------------------------------------------------------------------

def create_user(name, email):
    """INSERT a new user. Returns the new user's id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)",
        (name, email, datetime.now().isoformat())
    )
    # We use "?" placeholders, NEVER f-strings/string concatenation to
    # build SQL. This is a genuinely important interview point --
    # string-concatenated SQL is how SQL injection vulnerabilities happen.
    # Placeholders let SQLite treat user input strictly as DATA, never as
    # part of the SQL command itself.
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_user_by_email(email):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# PORTFOLIO OPERATIONS
# ---------------------------------------------------------------------------

def create_portfolio(user_id, name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO portfolios (user_id, name, created_at) VALUES (?, ?, ?)",
        (user_id, name, datetime.now().isoformat())
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def get_portfolios_for_user(user_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM portfolios WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# HOLDINGS OPERATIONS
# ---------------------------------------------------------------------------

def get_holding(portfolio_id, symbol):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM holdings WHERE portfolio_id = ? AND symbol = ?",
        (portfolio_id, symbol)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_holding(portfolio_id, symbol, quantity, avg_buy_price, sector, conn=None):
    """
    INSERT a new holding row, or UPDATE the existing one if this
    portfolio+symbol combination already exists.

    "Upsert" (update-or-insert) is a real, commonly-used pattern.
    SQLite supports it natively via "ON CONFLICT", relying on the
    UNIQUE(portfolio_id, symbol) constraint we defined in init_db().

    ATOMICITY NOTE: accepts an optional shared `conn`. If the caller
    passes one in (e.g. buy_stock() coordinating this with
    add_transaction()), we use it and deliberately do NOT commit or
    close here -- the caller owns the transaction lifecycle. If no
    conn is passed, we fall back to the old standalone behavior, so
    this function still works independently wherever it's called alone.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO holdings (portfolio_id, symbol, quantity, avg_buy_price, sector, last_updated)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(portfolio_id, symbol)
        DO UPDATE SET quantity = ?, avg_buy_price = ?, sector = ?, last_updated = ?
    """, (
        portfolio_id, symbol, quantity, avg_buy_price, sector, datetime.now().isoformat(),
        quantity, avg_buy_price, sector, datetime.now().isoformat()
    ))

    if owns_connection:
        conn.commit()
        conn.close()


def delete_holding(portfolio_id, symbol, conn=None):
    """
    Same shared-connection pattern as upsert_holding()/add_transaction() --
    lets sell_stock() include this in the same atomic transaction when a
    position is fully sold out.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()

    cur = conn.cursor()
    cur.execute(
        "DELETE FROM holdings WHERE portfolio_id = ? AND symbol = ?",
        (portfolio_id, symbol)
    )

    if owns_connection:
        conn.commit()
        conn.close()


def get_holdings(portfolio_id):
    """
    SELECT with ORDER BY -- returns all current holdings for a portfolio,
    sorted by symbol for consistent, predictable display order.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM holdings WHERE portfolio_id = ? ORDER BY symbol ASC",
        (portfolio_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# TRANSACTION OPERATIONS
# ---------------------------------------------------------------------------

def add_transaction(portfolio_id, symbol, type_, quantity, price, conn=None):
    """
    INSERT a new row into the immutable transaction ledger.
    This is called every single time a BUY or SELL happens -- it is the
    permanent record. holdings gets updated separately (see portfolio.py),
    but this table is never modified after insertion.

    ATOMICITY NOTE: same shared-connection pattern as upsert_holding().
    When called as part of buy_stock()/sell_stock(), this and
    upsert_holding() run on the SAME connection, so they commit or
    rollback together as one atomic unit.
    """
    owns_connection = conn is None
    if owns_connection:
        conn = get_connection()

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO transactions (portfolio_id, symbol, type, quantity, price, transaction_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (portfolio_id, symbol, type_, quantity, price, datetime.now().isoformat()))

    if owns_connection:
        conn.commit()
        conn.close()


def get_transactions(portfolio_id, symbol=None):
    """
    SELECT transaction history. If symbol is given, filter to just that
    stock; otherwise return the full history for the portfolio.
    Demonstrates conditional/dynamic SQL building based on a parameter --
    a common real-world pattern.
    """
    conn = get_connection()
    cur = conn.cursor()
    if symbol:
        cur.execute("""
            SELECT * FROM transactions
            WHERE portfolio_id = ? AND symbol = ?
            ORDER BY transaction_date DESC
        """, (portfolio_id, symbol))
    else:
        cur.execute("""
            SELECT * FROM transactions
            WHERE portfolio_id = ?
            ORDER BY transaction_date DESC
        """, (portfolio_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_transaction_summary(portfolio_id):
    """
    Demonstrates GROUP BY + aggregate functions (SUM, COUNT) -- a very
    likely thing to be asked to explain live in an interview.

    For each symbol traded in this portfolio, this returns:
    - total number of transactions
    - total quantity bought
    - total quantity sold
    This is the kind of query a real analytics dashboard would run to
    build a "trading activity" summary view.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            symbol,
            COUNT(*) AS num_transactions,
            SUM(CASE WHEN type = 'BUY' THEN quantity ELSE 0 END) AS total_bought,
            SUM(CASE WHEN type = 'SELL' THEN quantity ELSE 0 END) AS total_sold
        FROM transactions
        WHERE portfolio_id = ?
        GROUP BY symbol
        ORDER BY num_transactions DESC
    """, (portfolio_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_portfolio_with_user(portfolio_id):
    """
    Demonstrates a JOIN -- another near-guaranteed interview ask.
    Combines the portfolios table with users table to answer:
    "which user owns this portfolio, and what's their name/email?"
    Without a JOIN, we'd need two separate queries and combine them in
    Python -- the JOIN lets the database do that work in one query.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            portfolios.id AS portfolio_id,
            portfolios.name AS portfolio_name,
            users.name AS owner_name,
            users.email AS owner_email
        FROM portfolios
        JOIN users ON portfolios.user_id = users.id
        WHERE portfolios.id = ?
    """, (portfolio_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
