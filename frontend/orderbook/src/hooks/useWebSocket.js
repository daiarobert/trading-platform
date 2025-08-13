import { useState, useEffect, useRef } from "react";
import { io } from "socket.io-client";
import toast from "react-hot-toast";

export const useWebSocket = () => {
  const [connected, setConnected] = useState(false);
  const [orderbook, setOrderbook] = useState([]);
  const socketRef = useRef(null);

  const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL || "http://localhost:5000";

  useEffect(() => {
    console.log("🔌 Attempting WebSocket connection to:", API_BASE_URL);

    // Create socket connection
    const socket = io(API_BASE_URL, {
      transports: ["websocket", "polling"],
      timeout: 10000,
      forceNew: true,
    });

    // Connection events
    socket.on("connect", () => {
      console.log("✅ WebSocket connected successfully");
      setConnected(true);
      toast.success("Real-time connection established", { duration: 2000 });

      // Subscribe to orderbook updates
      console.log("📡 Subscribing to orderbook updates");
      socket.emit("subscribe_orderbook");
    });

    socket.on("disconnect", (reason) => {
      console.log("❌ WebSocket disconnected:", reason);
      setConnected(false);
      if (reason !== "io client disconnect") {
        toast.error("Real-time connection lost", { duration: 2000 });
      }
    });

    socket.on("connect_error", (error) => {
      console.error("❌ WebSocket connection error:", error);
      setConnected(false);
      toast.error("Failed to connect to real-time updates", { duration: 3000 });
    });

    // Data events
    socket.on("orderbook_update", (data) => {
      console.log("📊 Received orderbook update:", data?.length || 0, "orders");
      if (Array.isArray(data)) {
        setOrderbook(data);
      } else {
        console.warn("⚠️ Invalid orderbook data received:", data);
      }
    });

    socketRef.current = socket;

    // Cleanup on unmount
    return () => {
      socket.disconnect();
    };
  }, [API_BASE_URL]);

  return {
    connected,
    orderbook,
  };
};
