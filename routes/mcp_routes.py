"""WebSocket MCP routes for MCP server communication."""

import logging
import uuid
from datetime import datetime
from typing import Dict, Any
from flask import request
from flask_socketio import emit

logger = logging.getLogger(__name__)

# Store active MCP connections (in production, use Redis or database)
mcp_connections: Dict[str, Dict[str, Any]] = {}


def register_mcp_events(socketio):
    """
    Register all MCP WebSocket event handlers with SocketIO.
    
    Args:
        socketio: SocketIO instance to register events with
    """
    
    @socketio.on('connect', namespace='/mcp')
    def handle_mcp_connect():
        """Handle MCP server WebSocket connection."""
        try:
            connection_id = str(uuid.uuid4())
            client_ip = request.remote_addr
            origin = request.headers.get('Origin', 'unknown')
            
            logger.info(f"MCP server connection attempt from {client_ip} (Origin: {origin})")
            
            # Store connection information
            mcp_connections[connection_id] = {
                'connection_id': connection_id,
                'connected_at': datetime.utcnow().isoformat(),
                'client_ip': client_ip,
                'origin': origin,
                'sid': request.sid
            }
            
            # Emit connection confirmation
            emit('connected', {
                'connection_id': connection_id,
                'status': 'connected',
                'message': 'MCP WebSocket connection established',
                'timestamp': datetime.utcnow().isoformat()
            }, namespace='/mcp', callback=lambda: logger.debug(f"Connected event sent for MCP connection {connection_id}"))
            
            logger.info(f"MCP server connection established - Connection ID: {connection_id}, SID: {request.sid}")
            
            return True  # Accept the connection
            
        except Exception as e:
            logger.error(f"Error handling MCP WebSocket connection: {e}", exc_info=True)
            try:
                emit('error', {
                    'type': 'connection_error',
                    'message': f'Failed to establish MCP connection: {str(e)}',
                    'timestamp': datetime.utcnow().isoformat()
                }, namespace='/mcp')
            except:
                pass  # If we can't emit, at least log it
            return False  # Reject the connection
    
    
    @socketio.on('disconnect', namespace='/mcp')
    def handle_mcp_disconnect(*args, **kwargs):
        """Handle MCP server WebSocket disconnection."""
        try:
            sid = request.sid if hasattr(request, 'sid') else None
            
            if not sid:
                logger.warning("MCP WebSocket disconnect called but no SID available")
                return
            
            # Find and remove connection by SID
            connection_to_remove = None
            for connection_id, connection_data in mcp_connections.items():
                if connection_data.get('sid') == sid:
                    connection_to_remove = connection_id
                    break
            
            if connection_to_remove:
                connection_data = mcp_connections.pop(connection_to_remove)
                logger.info(f"MCP server disconnected - Connection ID: {connection_to_remove}, SID: {sid}")
            else:
                logger.warning(f"MCP server disconnect for unknown SID: {sid}")
                
        except Exception as e:
            logger.error(f"Error handling MCP WebSocket disconnection: {e}", exc_info=True)
    
    
    logger.info("MCP event handlers registered successfully")
