"""
Transaction-related routes for viewing transaction history.
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from db_pool import get_db_connection
import mysql.connector
import logging

# Import helper functions
from helpers import get_user_id_int

transaction_bp = Blueprint('transactions', __name__)


@transaction_bp.route("/transactions", methods=["GET"])
@jwt_required()
def get_transactions():
    """Get all recent transactions (public transaction history)."""
    try:
        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT t.*, 
                       bo.user_id as buyer_id,
                       so.user_id as seller_id
                FROM transactions t
                LEFT JOIN orders bo ON t.buy_order_id = bo.id
                LEFT JOIN orders so ON t.sell_order_id = so.id
                ORDER BY t.executed_at DESC
                LIMIT 100
            """
            )
            transactions = cursor.fetchall()
            cursor.close()

            return jsonify({"success": True, "transactions": transactions})

    except mysql.connector.Error as err:
        logging.error(f"Error fetching transactions: {err}")
        return jsonify({"error": "Database error"}), 500


@transaction_bp.route("/user/transactions", methods=["GET"])
@jwt_required()
def get_user_transactions():
    """Get current user's transaction history."""
    try:
        user_id = get_user_id_int()

        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT t.*, 
                       bo.user_id as buyer_id,
                       so.user_id as seller_id,
                       CASE 
                           WHEN bo.user_id = %s THEN 'BUY'
                           WHEN so.user_id = %s THEN 'SELL'
                           ELSE 'UNKNOWN'
                       END as user_side
                FROM transactions t
                LEFT JOIN orders bo ON t.buy_order_id = bo.id
                LEFT JOIN orders so ON t.sell_order_id = so.id
                WHERE bo.user_id = %s OR so.user_id = %s
                ORDER BY t.executed_at DESC
                LIMIT 100
            """,
                (user_id, user_id, user_id, user_id),
            )
            transactions = cursor.fetchall()
            cursor.close()

            return jsonify({"success": True, "transactions": transactions})

    except mysql.connector.Error as err:
        logging.error(f"Error fetching user transactions: {err}")
        return jsonify({"error": "Database error"}), 500
