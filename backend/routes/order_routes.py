"""
Order-related routes for creating, reading, updating, and deleting orders.
"""

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from db_pool import get_db_connection
import mysql.connector
import logging

# Import helper functions
from helpers import (
    get_user_id_int,
    reserve_balance_for_order,
    release_balance_for_order,
    match_orders,
)

order_bp = Blueprint('orders', __name__)


@order_bp.route("/orders", methods=["GET"])
@jwt_required()
def get_orders():
    """Get all active orders in the orderbook."""
    try:
        current_user_id = get_user_id_int()

        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id, user_id, symbol, side, price, quantity, status, 
                       filled_quantity, created_at, updated_at,
                       CASE WHEN user_id = %s THEN true ELSE false END as is_own_order
                FROM orders 
                WHERE status IN ('PENDING', 'PARTIAL')
                ORDER BY 
                    symbol ASC,
                    CASE WHEN side = 'BUY' THEN price END DESC,
                    CASE WHEN side = 'SELL' THEN price END ASC,
                    created_at ASC
            """,
                (current_user_id,),
            )
            orders = cursor.fetchall()
            cursor.close()

            return jsonify(orders)

    except mysql.connector.Error as err:
        logging.error(f"Error fetching orders: {err}")
        return Response(status=500)


@order_bp.route("/user/orders", methods=["GET"])
@jwt_required()
def get_user_orders():
    """Get current user's orders."""
    try:
        user_id = get_user_id_int()

        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT id, symbol, side, price, quantity, status, 
                       filled_quantity, created_at, updated_at
                FROM orders 
                WHERE user_id = %s 
                ORDER BY created_at DESC
            """,
                (user_id,),
            )
            orders = cursor.fetchall()
            cursor.close()

            return jsonify({"success": True, "orders": orders})

    except mysql.connector.Error as err:
        logging.error(f"Error fetching user orders: {err}")
        return jsonify({"error": "Database error"}), 500


@order_bp.route("/orders", methods=["POST"])
@jwt_required()
def create_order():
    """Create a new order."""
    try:
        user_id = get_user_id_int()

        # Validate required fields
        required_fields = ["symbol", "side", "quantity"]
        for field in required_fields:
            if field not in request.json:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Get and validate data
        symbol = request.json["symbol"]
        side = request.json["side"].upper()
        quantity = float(request.json["quantity"])
        price = float(request.json.get("price", 0))
        order_type = request.json.get("order_type", "LIMIT")

        # Validate values
        if quantity <= 0:
            return jsonify({"error": "Quantity must be greater than 0"}), 400
        if order_type != "MARKET" and price <= 0:
            return (
                jsonify(
                    {"error": "Price must be greater than 0 for non-market orders"}
                ),
                400,
            )
        if side not in ["BUY", "SELL"]:
            return jsonify({"error": "Side must be either 'BUY' or 'SELL'"}), 400

        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)

            # Reserve balance for the order
            try:
                reserve_balance_for_order(
                    cursor, user_id, side, symbol, quantity, price
                )
            except ValueError as e:
                cursor.close()
                return jsonify({"error": str(e)}), 400

            # Insert order
            cursor.execute(
                """
                INSERT INTO orders (
                    user_id, symbol, side, price, quantity, 
                    status, filled_quantity, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, 'PENDING', 0.0, NOW(), NOW())
            """,
                (user_id, symbol, side, price, quantity),
            )

            db.commit()
            order_id = cursor.lastrowid

            # Attempt to match the new order
            try:
                match_orders(cursor, order_id, db)
                db.commit()
                logging.info(f"Order matching completed for order {order_id}")
            except Exception as match_error:
                logging.error(f"Error during order matching: {match_error}")
                db.rollback()
                db.commit()

            cursor.close()

            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Order created successfully",
                        "order": {
                            "id": order_id,
                            "user_id": user_id,
                            "symbol": symbol,
                            "side": side,
                            "price": price,
                            "quantity": quantity,
                            "status": "PENDING",
                            "filled_quantity": 0.0,
                        },
                    }
                ),
                201,
            )

    except ValueError as e:
        return jsonify({"error": "Invalid numeric value provided"}), 400
    except mysql.connector.Error as err:
        logging.error(f"Error creating order: {err}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return jsonify({"error": "Internal server error"}), 500


@order_bp.route("/orders/<int:order_id>", methods=["GET"])
@jwt_required()
def get_order(order_id):
    """Get a specific order by ID."""
    try:
        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)
            sql = "SELECT * FROM orders WHERE id = %s"
            cursor.execute(sql, (order_id,))
            order = cursor.fetchone()
            cursor.close()

        if order:
            return jsonify(order)
        else:
            return Response(status=404)
    except mysql.connector.Error as err:
        logging.error(f"Error fetching order: {err}")
        return Response(status=500)


@order_bp.route("/orders/<int:order_id>", methods=["DELETE"])
@jwt_required()
def delete_order(order_id):
    """Cancel an existing order."""
    try:
        user_id = get_user_id_int()

        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)

            # Get order details
            cursor.execute(
                "SELECT id, user_id, status, symbol, side, quantity, price, filled_quantity FROM orders WHERE id = %s",
                (order_id,),
            )
            order = cursor.fetchone()

            if not order:
                cursor.close()
                return jsonify({"error": "Order not found"}), 404

            if order["user_id"] != user_id:
                cursor.close()
                return jsonify({"error": "You can only delete your own orders"}), 403

            if order["status"] not in ["PENDING", "PARTIAL"]:
                cursor.close()
                return (
                    jsonify(
                        {
                            "error": f"Cannot delete order with status '{order['status']}'. Only PENDING and PARTIAL orders can be cancelled."
                        }
                    ),
                    400,
                )

            # Calculate remaining unfilled quantity and release reserved balances
            filled_quantity = float(order.get("filled_quantity", 0))
            remaining_quantity = float(order["quantity"]) - filled_quantity

            if remaining_quantity > 0:
                try:
                    release_balance_for_order(
                        cursor,
                        user_id,
                        order["side"],
                        order["symbol"],
                        remaining_quantity,
                        float(order["price"]),
                    )
                except ValueError as e:
                    cursor.close()
                    return jsonify({"error": str(e)}), 500

            # Mark order as CANCELLED
            cursor.execute(
                "UPDATE orders SET status = 'CANCELLED', updated_at = NOW() WHERE id = %s AND user_id = %s",
                (order_id, user_id),
            )
            db.commit()
            cursor.close()

            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Order cancelled and balances released successfully",
                    }
                ),
                200,
            )

    except mysql.connector.Error as err:
        logging.error(f"Error deleting order: {err}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error deleting order: {e}")
        return jsonify({"error": "Internal server error"}), 500


@order_bp.route("/orders/<int:order_id>", methods=["PUT"])
@jwt_required()
def update_order(order_id):
    """Update an existing order."""
    try:
        user_id = get_jwt_identity()

        # Validate required fields
        required_fields = ["symbol", "side", "price", "quantity"]
        for field in required_fields:
            if field not in request.json:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Get new order data
        new_symbol = request.json["symbol"]
        new_side = request.json["side"].upper()
        new_price = float(request.json["price"])
        new_quantity = float(request.json["quantity"])

        # Validate new values
        if new_quantity <= 0:
            return jsonify({"error": "Quantity must be greater than 0"}), 400
        if new_price <= 0:
            return jsonify({"error": "Price must be greater than 0"}), 400
        if new_side not in ["BUY", "SELL"]:
            return jsonify({"error": "Side must be either 'BUY' or 'SELL'"}), 400

        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)

            # Check if the order exists and belongs to the user
            check_sql = "SELECT id, user_id, status, symbol, side, price, quantity, filled_quantity FROM orders WHERE id = %s"
            cursor.execute(check_sql, (order_id,))
            order = cursor.fetchone()

            if not order:
                cursor.close()
                return jsonify({"error": "Order not found"}), 404

            if int(order["user_id"]) != int(user_id):
                cursor.close()
                return jsonify({"error": "You can only update your own orders"}), 403

            if order["status"] not in ["PENDING", "PARTIAL"]:
                cursor.close()
                return (
                    jsonify(
                        {
                            "error": f"Cannot update order with status '{order['status']}'. Only PENDING and PARTIAL orders can be updated."
                        }
                    ),
                    400,
                )

            filled_quantity = float(order.get("filled_quantity", 0))

            # For partial orders, new quantity must be at least filled_quantity
            if order["status"] == "PARTIAL" and new_quantity < filled_quantity:
                cursor.close()
                return (
                    jsonify(
                        {
                            "error": f"Cannot reduce quantity below filled amount. Already filled: {filled_quantity}, Minimum new quantity: {filled_quantity}"
                        }
                    ),
                    400,
                )

            # Release old balance reservations for unfilled portion
            old_unfilled_quantity = float(order["quantity"]) - filled_quantity
            if old_unfilled_quantity > 0:
                try:
                    release_balance_for_order(
                        cursor,
                        int(user_id),
                        order["side"],
                        order["symbol"],
                        old_unfilled_quantity,
                        float(order["price"]),
                    )
                except ValueError as e:
                    cursor.close()
                    return jsonify({"error": str(e)}), 500

            # Reserve new balance for unfilled portion
            new_unfilled_quantity = new_quantity - filled_quantity
            if new_unfilled_quantity > 0:
                try:
                    reserve_balance_for_order(
                        cursor, int(user_id), new_side, new_symbol, new_unfilled_quantity, new_price
                    )
                except ValueError as e:
                    cursor.close()
                    return jsonify({"error": str(e)}), 400

            # Update the order
            update_sql = """
                UPDATE orders 
                SET symbol = %s, side = %s, price = %s, quantity = %s, updated_at = NOW()
                WHERE id = %s AND user_id = %s
            """
            cursor.execute(
                update_sql,
                (new_symbol, new_side, new_price, new_quantity, order_id, int(user_id)),
            )
            db.commit()

            if cursor.rowcount > 0:
                # Try to match the updated order with existing orders
                try:
                    match_orders(cursor, order_id, db)
                    db.commit()
                    logging.info(f"Order matching completed for updated order {order_id}")
                except Exception as match_error:
                    logging.error(f"Error during order matching for updated order: {match_error}")
                    db.rollback()
                    db.commit()
                
                cursor.close()
                return (
                    jsonify(
                        {
                            "success": True,
                            "message": "Order updated successfully with balance adjustments",
                        }
                    ),
                    200,
                )
            else:
                cursor.close()
                return jsonify({"error": "Failed to update order"}), 500

    except ValueError as e:
        return jsonify({"error": "Invalid numeric value provided"}), 400
    except mysql.connector.Error as err:
        logging.error(f"Error updating order: {err}")
        return jsonify({"error": "Database error"}), 500
    except Exception as e:
        logging.error(f"Unexpected error updating order: {e}")
        return jsonify({"error": "Internal server error"}), 500
