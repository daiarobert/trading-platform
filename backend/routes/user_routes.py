"""
User-related routes for balance management and user data.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from db_pool import get_db_connection
import mysql.connector
import logging

# Import helper functions
from helpers import get_user_id_int

user_bp = Blueprint('users', __name__)


@user_bp.route("/user/balances", methods=["GET"])
@jwt_required()
def get_user_balances():
    """Get current user's balances."""
    try:
        user_id = get_user_id_int()

        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT asset, available, reserved, updated_at
                FROM balances 
                WHERE user_id = %s 
                ORDER BY asset
            """,
                (user_id,),
            )
            balances = cursor.fetchall()
            cursor.close()

            # Convert to a more convenient format for frontend
            balance_dict = {}
            for balance in balances:
                balance_dict[balance["asset"]] = {
                    "available": float(balance["available"]),
                    "reserved": float(balance["reserved"]),
                    "total": float(balance["available"]) + float(balance["reserved"]),
                    "updated_at": (
                        balance["updated_at"].isoformat()
                        if balance["updated_at"]
                        else None
                    ),
                }

            return jsonify({"success": True, "balances": balance_dict})

    except mysql.connector.Error as err:
        logging.error(f"Error fetching user balances: {err}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error fetching balances: {e}")
        return jsonify({"error": "Internal server error"}), 500


@user_bp.route("/user/balances/<asset>", methods=["PUT"])
@jwt_required()
def update_user_balance(asset):
    """Update user balance for a specific asset (for deposits/withdrawals)."""
    try:
        user_id = get_jwt_identity()

        # Validate required fields
        if "available" not in request.json:
            return jsonify({"error": "Missing required field: available"}), 400

        available = float(request.json["available"])
        reserved = float(request.json.get("reserved", 0))

        if available < 0 or reserved < 0:
            return jsonify({"error": "Balance amounts cannot be negative"}), 400

        with get_db_connection() as db:
            cursor = db.cursor()

            # Check if balance record exists
            cursor.execute(
                "SELECT id FROM balances WHERE user_id = %s AND asset = %s",
                (int(user_id), asset.upper()),
            )
            existing = cursor.fetchone()

            if existing:
                # Update existing balance
                cursor.execute(
                    """UPDATE balances 
                       SET available = %s, reserved = %s, updated_at = NOW()
                       WHERE user_id = %s AND asset = %s""",
                    (available, reserved, int(user_id), asset.upper()),
                )
            else:
                # Create new balance record
                cursor.execute(
                    """INSERT INTO balances (user_id, asset, available, reserved, updated_at)
                       VALUES (%s, %s, %s, %s, NOW())""",
                    (int(user_id), asset.upper(), available, reserved),
                )

            db.commit()
            cursor.close()

            return (
                jsonify(
                    {"success": True, "message": f"Balance updated for {asset.upper()}"}
                ),
                200,
            )

    except ValueError as e:
        return jsonify({"error": "Invalid numeric value provided"}), 400
    except mysql.connector.Error as err:
        logging.error(f"Error updating balance: {err}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error updating balance: {e}")
        return jsonify({"error": "Internal server error"}), 500
