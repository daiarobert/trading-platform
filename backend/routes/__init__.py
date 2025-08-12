"""
Routes package initialization.
Registers all route blueprints.
"""

from .auth_routes import auth_bp
from .order_routes import order_bp
from .user_routes import user_bp
from .transaction_routes import transaction_bp

def register_routes(app):
    """Register all route blueprints with the Flask app."""
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(order_bp, url_prefix='/api')
    app.register_blueprint(user_bp, url_prefix='/api')
    app.register_blueprint(transaction_bp, url_prefix='/api')
