"""
Simple WebSocket Manager for Trading Platform
"""
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import request
import threading
import time
from db_pool import get_db_connection

class WebSocketManager:
    def __init__(self, app=None):
        self.socketio = None
        self.last_orderbook_hash = None
        self.monitoring = False
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize SocketIO with Flask app"""
        self.socketio = SocketIO(
            app, 
            cors_allowed_origins="*",
            logger=False,
            engineio_logger=False
        )
        self.setup_events()
        self.start_monitoring()
    
    def setup_events(self):
        """Setup WebSocket event handlers"""
        
        @self.socketio.on('connect')
        def handle_connect(auth):
            print(f'Client connected: {request.sid}')
            # Send initial orderbook data
            self.send_orderbook_update(request.sid)
        
        @self.socketio.on('disconnect')
        def handle_disconnect():
            print(f'Client disconnected: {request.sid}')
        
        @self.socketio.on('subscribe_orderbook')
        def handle_subscribe():
            print(f'Client {request.sid} subscribed to orderbook')
            join_room('orderbook')
            self.send_orderbook_update(request.sid)
    
    def get_orderbook_data(self):
        """Get current orderbook from database"""
        try:
            with get_db_connection() as connection:
                cursor = connection.cursor(dictionary=True)
            
            query = """
            SELECT id, user_id, symbol, side, quantity, price, status, 
                   filled_quantity, created_at, updated_at 
            FROM orders 
            WHERE status IN ('PENDING', 'PARTIAL')
            ORDER BY 
                CASE WHEN side = 'BUY' THEN price END DESC,
                CASE WHEN side = 'SELL' THEN price END ASC,
                created_at ASC
            """
            cursor.execute(query)
            orders = cursor.fetchall()
            
            # Convert datetime to string and Decimal to float
            for order in orders:
                if order['created_at']:
                    order['created_at'] = order['created_at'].isoformat()
                if order['updated_at']:
                    order['updated_at'] = order['updated_at'].isoformat()
                # Convert Decimal fields to float for JSON serialization
                if 'price' in order and order['price'] is not None:
                    order['price'] = float(order['price'])
                if 'quantity' in order and order['quantity'] is not None:
                    order['quantity'] = float(order['quantity'])
                if 'filled_quantity' in order and order['filled_quantity'] is not None:
                    order['filled_quantity'] = float(order['filled_quantity'])
            
            return orders
        except Exception as e:
            print(f"Error getting orderbook: {e}")
            return []
    
    def send_orderbook_update(self, sid=None):
        """Send orderbook update to client(s)"""
        try:
            orderbook = self.get_orderbook_data()
            if sid:
                # Send to specific client
                self.socketio.emit('orderbook_update', orderbook, room=sid)
            else:
                # Broadcast to all clients
                self.socketio.emit('orderbook_update', orderbook, room='orderbook')
        except Exception as e:
            print(f"Error sending orderbook update: {e}")
    
    def broadcast_orderbook_change(self):
        """Broadcast orderbook changes to all subscribed clients"""
        self.send_orderbook_update()
    
    def monitor_orderbook_changes(self):
        """Monitor database for changes and broadcast updates"""
        while self.monitoring:
            try:
                with get_db_connection() as connection:
                    cursor = connection.cursor()
                
                # Get hash of current orderbook state
                cursor.execute("""
                    SELECT COUNT(*), MAX(updated_at) 
                    FROM orders 
                    WHERE status IN ('PENDING', 'PARTIAL')
                """)
                result = cursor.fetchone()
                current_hash = str(result) if result else ""
                
                # If orderbook changed, broadcast update
                if current_hash != self.last_orderbook_hash:
                    self.broadcast_orderbook_change()
                    self.last_orderbook_hash = current_hash
                
            except Exception as e:
                print(f"Error monitoring orderbook: {e}")
            
            time.sleep(0.5)  # Check every 0.5 seconds for faster updates
    
    def start_monitoring(self):
        """Start background monitoring thread"""
        if not self.monitoring:
            self.monitoring = True
            monitor_thread = threading.Thread(target=self.monitor_orderbook_changes, daemon=True)
            monitor_thread.start()
            print("Started orderbook monitoring")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring = False

# Global instance
ws_manager = WebSocketManager()
