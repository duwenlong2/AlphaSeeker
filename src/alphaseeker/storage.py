from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Literal

DB_PATH = Path("data/alphaseeker.db")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_storage() -> None:
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holdings (
                symbol TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                quantity REAL NOT NULL,
                cost_price REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                fee REAL NOT NULL DEFAULT 0,
                amount REAL NOT NULL,
                trade_time TEXT NOT NULL,
                note TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holdings_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                quantity REAL NOT NULL,
                cost_price REAL NOT NULL,
                market_price REAL,
                market_value REAL,
                unrealized_pnl_pct REAL
            )
            """
        )


def upsert_holding(symbol: str, name: str, quantity: float, cost_price: float) -> None:
    now = datetime.utcnow().isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO holdings(symbol, name, quantity, cost_price, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                name=excluded.name,
                quantity=excluded.quantity,
                cost_price=excluded.cost_price,
                updated_at=excluded.updated_at
            """,
            (symbol, name, quantity, cost_price, now),
        )


def delete_holding(symbol: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,))


def list_holdings() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT symbol, name, quantity, cost_price, updated_at FROM holdings ORDER BY symbol"
        ).fetchall()
    return [dict(r) for r in rows]


def apply_trade(
    side: Literal["buy", "sell"],
    symbol: str,
    name: str,
    quantity: float,
    price: float,
    fee: float = 0.0,
    note: str = "",
    trade_time: str | None = None,
) -> None:
    if quantity <= 0 or price <= 0:
        raise ValueError("quantity 和 price 必须大于 0")
    if fee < 0:
        raise ValueError("fee 不能为负数")

    now = datetime.utcnow().isoformat()
    trade_time = trade_time or now
    amount = quantity * price
    symbol = symbol.upper().strip()

    with _conn() as conn:
        row = conn.execute(
            "SELECT symbol, name, quantity, cost_price FROM holdings WHERE symbol = ?",
            (symbol,),
        ).fetchone()

        current_qty = float(row["quantity"]) if row else 0.0
        current_cost = float(row["cost_price"]) if row else 0.0

        if side == "buy":
            total_cost = current_qty * current_cost + amount + fee
            new_qty = current_qty + quantity
            new_cost = total_cost / new_qty
            conn.execute(
                """
                INSERT INTO holdings(symbol, name, quantity, cost_price, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name=excluded.name,
                    quantity=excluded.quantity,
                    cost_price=excluded.cost_price,
                    updated_at=excluded.updated_at
                """,
                (symbol, name, new_qty, new_cost, now),
            )
        elif side == "sell":
            if current_qty <= 0:
                raise ValueError(f"无持仓可卖出: {symbol}")
            if quantity > current_qty:
                raise ValueError(f"卖出数量超过持仓: {quantity} > {current_qty}")

            new_qty = current_qty - quantity
            if new_qty == 0:
                conn.execute("DELETE FROM holdings WHERE symbol = ?", (symbol,))
            else:
                conn.execute(
                    "UPDATE holdings SET quantity = ?, updated_at = ? WHERE symbol = ?",
                    (new_qty, now, symbol),
                )
        else:
            raise ValueError(f"不支持的 side: {side}")

        conn.execute(
            """
            INSERT INTO trades(
                symbol, name, side, quantity, price, fee, amount, trade_time, note, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (symbol, name, side, quantity, price, fee, amount, trade_time, note, now),
        )


def list_trades(limit: int = 200) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT id, symbol, name, side, quantity, price, fee, amount, trade_time, note, created_at
            FROM trades
            ORDER BY datetime(trade_time) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_holdings_snapshot(rows: list[dict], snapshot_time: str | None = None) -> str:
    snapshot_time = snapshot_time or datetime.utcnow().isoformat()
    with _conn() as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO holdings_snapshots(
                    snapshot_time, symbol, name, quantity, cost_price,
                    market_price, market_value, unrealized_pnl_pct
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_time,
                    row.get("symbol"),
                    row.get("name"),
                    float(row.get("quantity", 0)),
                    float(row.get("cost_price", 0)),
                    row.get("current_price"),
                    row.get("market_value"),
                    row.get("pnl_pct"),
                ),
            )
    return snapshot_time


def list_snapshot_times(limit: int = 100) -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT snapshot_time, COUNT(*) as cnt
            FROM holdings_snapshots
            GROUP BY snapshot_time
            ORDER BY datetime(snapshot_time) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [str(r["snapshot_time"]) for r in rows]


def load_snapshot(snapshot_time: str) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT symbol, name, quantity, cost_price, market_price, market_value, unrealized_pnl_pct
            FROM holdings_snapshots
            WHERE snapshot_time = ?
            ORDER BY symbol
            """,
            (snapshot_time,),
        ).fetchall()
    return [dict(r) for r in rows]
