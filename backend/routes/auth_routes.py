"""
Authentication routes for login, register, and user authentication.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from db_pool import get_db_connection
import mysql.connector
import logging
import bcrypt

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/login", methods=["POST"])
def login():
    """User login endpoint."""
    try:
        email = request.json.get("email")
        password = request.json.get("password")

        if not email or not password:
            return jsonify({"message": "Email and password are required"}), 400

        with get_db_connection() as db:
            cursor = db.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            cursor.close()

        # Check password with bcrypt
        if user and bcrypt.checkpw(
            password.encode("utf-8"), user["password"].encode("utf-8")
        ):
            # Create JWT token - Convert user ID to string for Flask-JWT-Extended compatibility
            access_token = create_access_token(identity=str(user["id"]))

            response_data = {
                "success": True,
                "token": access_token,
                "expiresIn": 60 * 60,  # 1 hour in seconds
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "username": user["username"],
                    "created_at": (
                        user["created_at"].isoformat()
                        if user.get("created_at")
                        else None
                    ),
                },
            }

            return jsonify(response_data), 200
        else:
            return jsonify({"message": "Invalid email or password"}), 401

    except mysql.connector.Error as err:
        logging.error(f"Error logging in: {err}")
        return jsonify({"error": "Database error"}), 500


@auth_bp.route("/register", methods=["POST"])
def register():
    """User registration endpoint."""
    try:
        email = request.json.get("email")
        password = request.json.get("password")
        username = request.json.get("username", email)

        if not email or not password:
            return jsonify({"message": "Email and password are required"}), 400

        hashed_password = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        with get_db_connection() as db:
            cursor = db.cursor()

            # Insert user
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, hashed_password),
            )
            user_id = cursor.lastrowid

            # Create demo balances for new user
            demo_balances = [
                ("USD", 10000.00, 0.00),  # $10,000 USD
                ("BTC", 0.5, 0.00),  # 0.5 BTC
                ("ETH", 2.0, 0.00),  # 2.0 ETH
                ("ADA", 1000.0, 0.00),  # 1,000 ADA
                ("SOL", 50.0, 0.00),  # 50 SOL
            ]

            for asset, available, reserved in demo_balances:
                cursor.execute(
                    """INSERT INTO balances (user_id, asset, available, reserved, updated_at) 
                       VALUES (%s, %s, %s, %s, NOW())""",
                    (user_id, asset, available, reserved),
                )

            db.commit()
            cursor.close()

            return (
                jsonify({"message": "User registered successfully with demo balances"}),
                201,
            )

    except mysql.connector.Error as err:
        logging.error(f"Error registering user: {err}")
        return jsonify({"error": "Database error"}), 500
