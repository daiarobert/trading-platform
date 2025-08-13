import { useState, useEffect, useCallback, useMemo } from "react";
import { fetchOrderBook } from "../services/api";
import { useWebSocket } from "./useWebSocket";
import { getCurrentUser } from "../services/authService";
import {
  groupOrdersByPrice,
  separateOrdersBySide,
  calculateSpread,
} from "../utils/orderUtils";

export const useOrderBook = (selectedSymbol = "BTCUSD") => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Use WebSocket for real-time data
  const { connected: wsConnected, orderbook: wsOrderbook } = useWebSocket();

  // Fallback API fetching when WebSocket is not connected
  const loadOrders = useCallback(async () => {
    try {
      setError("");
      const ordersArray = await fetchOrderBook();
      setOrders(ordersArray);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Use WebSocket data when available, fallback to API polling
  useEffect(() => {
    if (wsConnected && wsOrderbook && Array.isArray(wsOrderbook)) {
      console.log("📡 Using WebSocket data");

      // Add is_own_order flag to WebSocket data
      const currentUser = getCurrentUser();
      const currentUserId = currentUser?.id;

      const ordersWithOwnership = wsOrderbook.map((order) => ({
        ...order,
        is_own_order: currentUserId && order.user_id === currentUserId,
      }));

      setOrders(ordersWithOwnership);
      setError("");
      setLoading(false);
    } else if (!wsConnected) {
      console.log("🔄 Using API fallback - WebSocket not connected");
      loadOrders();
      const interval = setInterval(loadOrders, 5000);
      return () => clearInterval(interval);
    }
  }, [wsConnected, wsOrderbook, loadOrders]);

  // Initial load regardless of WebSocket status
  useEffect(() => {
    loadOrders();
  }, [loadOrders]);

  // Get available symbols
  const availableSymbols = useMemo(() => {
    return [...new Set(orders.map((order) => order.symbol))].sort();
  }, [orders]);

  // Process orders (memoized for performance)
  const processedData = useMemo(() => {
    // Filter orders by selected symbol
    const filteredOrders = orders.filter(
      (order) => order.symbol === selectedSymbol
    );

    const { bids, asks } = separateOrdersBySide(filteredOrders);
    const groupedBids = groupOrdersByPrice(bids);
    const groupedAsks = groupOrdersByPrice(asks);
    const spread = calculateSpread(groupedBids, groupedAsks);

    return {
      bids,
      asks,
      groupedBids,
      groupedAsks,
      spread,
      stats: {
        totalOrders: filteredOrders.length,
        bidCount: bids.length,
        askCount: asks.length,
      },
    };
  }, [orders, selectedSymbol]);

  // Manual refresh
  const refetch = useCallback(() => {
    setLoading(true);
    loadOrders();
  }, [loadOrders]);

  return {
    // Raw data
    orders,
    loading,
    error,

    // Processed data
    ...processedData,

    // Actions
    refetch: loadOrders,

    // Status helpers
    isConnected: wsConnected || !error,
    hasData: processedData.stats.totalOrders > 0,
    wsConnected,

    // Available symbols for dropdown
    availableSymbols,
  };
};
