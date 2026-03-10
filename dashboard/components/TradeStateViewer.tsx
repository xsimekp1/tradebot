"use client";

import React, { useState, useMemo } from "react";
import {
  AreaChart, Area, XAxis, YAxis, ResponsiveContainer,
  ReferenceLine, Tooltip,
} from "recharts";

type TradeEntry = {
  action: "open" | "close";
  side: "long" | "short";
  price: number;
  ts: string;
  fee: number;
  score?: number;
  spread?: number;
  close_reason?: "signal" | "stop_loss";
  pnl?: number;
  support?: number;
  resistance?: number;
  position_pct?: number;
  price_history?: number[];
};

export function TradeStateViewer({ trades }: { trades: TradeEntry[] }) {
  const [currentIndex, setCurrentIndex] = useState(0);

  // Group trades into open/close pairs
  const tradePairs = useMemo(() => {
    const pairs: { open: TradeEntry; close?: TradeEntry }[] = [];
    let currentOpen: TradeEntry | null = null;

    for (const trade of trades) {
      if (trade.action === "open") {
        if (currentOpen) {
          pairs.push({ open: currentOpen });
        }
        currentOpen = trade;
      } else if (trade.action === "close" && currentOpen) {
        pairs.push({ open: currentOpen, close: trade });
        currentOpen = null;
      }
    }
    if (currentOpen) {
      pairs.push({ open: currentOpen });
    }
    return pairs;
  }, [trades]);

  if (!tradePairs.length) {
    return (
      <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
        <h3 className="text-xs text-gray-500 uppercase tracking-wide mb-3">Trade State Viewer</h3>
        <p className="text-sm text-gray-600">No trades to display</p>
      </div>
    );
  }

  const pair = tradePairs[currentIndex];
  const canPrev = currentIndex > 0;
  const canNext = currentIndex < tradePairs.length - 1;

  const formatTime = (ts: string) => {
    return new Date(ts).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  };

  const formatPct = (val: number | undefined) => {
    if (val === undefined) return "—";
    return `${(val * 100).toFixed(1)}%`;
  };

  // Build chart data from price histories
  const chartData = useMemo(() => {
    const openHist = pair.open.price_history || [];
    const closeHist = pair.close?.price_history || [];

    // Combine: entry context (before entry) + trade duration (entry to exit)
    const combined: { idx: number; price: number; phase: "before" | "during" }[] = [];

    // Add entry context (3h before entry)
    openHist.forEach((p, i) => {
      combined.push({ idx: i, price: p, phase: "before" });
    });

    // Add trade duration prices (if we have close data)
    if (closeHist.length > 0) {
      const offset = combined.length;
      closeHist.forEach((p, i) => {
        combined.push({ idx: offset + i, price: p, phase: "during" });
      });
    }

    return combined;
  }, [pair]);

  // Calculate stop loss price
  const stopLossPrice = useMemo(() => {
    if (pair.open.spread === undefined) return null;
    const stopDist = Math.max(pair.open.spread / 2, pair.open.price * 0.01);
    return pair.open.side === "long"
      ? pair.open.price - stopDist
      : pair.open.price + stopDist;
  }, [pair.open]);

  // Find entry index in chart (where "before" phase ends)
  const entryIdx = useMemo(() => {
    const beforeCount = (pair.open.price_history || []).length;
    return beforeCount > 0 ? beforeCount - 1 : 0;
  }, [pair.open]);

  const TradePanel = ({ trade, label }: { trade: TradeEntry; label: string }) => (
    <div className="bg-[#0f1117] rounded-lg p-3 flex-1">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-gray-500 uppercase">{label}</span>
        <span className={`text-xs font-medium px-2 py-0.5 rounded ${
          trade.side === "long" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
        }`}>
          {trade.side.toUpperCase()}
        </span>
      </div>
      <p className="text-white font-bold text-lg">${trade.price.toFixed(2)}</p>
      <p className="text-xs text-gray-500">{formatTime(trade.ts)}</p>

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        {trade.score !== undefined && (
          <div>
            <span className="text-gray-500">Score</span>
            <p className={`font-medium ${trade.score >= 0 ? "text-green-400" : "text-red-400"}`}>
              {trade.score >= 0 ? "+" : ""}{trade.score.toFixed(3)}
            </p>
          </div>
        )}
        {trade.spread !== undefined && trade.action === "open" && (
          <div>
            <span className="text-gray-500">Stop Loss</span>
            {(() => {
              const stopDist = Math.max(trade.spread / 2, trade.price * 0.01);
              const stopPrice = trade.side === "long"
                ? trade.price - stopDist
                : trade.price + stopDist;
              return <p className="text-amber-400 font-medium">${stopPrice.toFixed(2)}</p>;
            })()}
          </div>
        )}
        {trade.close_reason && (
          <div>
            <span className="text-gray-500">Exit Reason</span>
            <p className={`font-medium ${trade.close_reason === "stop_loss" ? "text-amber-400" : "text-cyan-400"}`}>
              {trade.close_reason === "stop_loss" ? "Stop Loss" : "Signal"}
            </p>
          </div>
        )}
        {trade.pnl !== undefined && (
          <div>
            <span className="text-gray-500">P&L</span>
            <p className={`font-medium ${trade.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
              {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
            </p>
          </div>
        )}
      </div>
    </div>
  );

  const openTrade = pair.open;

  return (
    <div className="bg-[#1a1d27] rounded-xl border border-[#2a2d3a] p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xs text-gray-500 uppercase tracking-wide">
          Trade State Viewer
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">
            Trade {currentIndex + 1} / {tradePairs.length}
          </span>
          <button
            onClick={() => setCurrentIndex(currentIndex - 1)}
            disabled={!canPrev}
            className="p-1 rounded bg-[#2a2d3a] hover:bg-[#3a3d4a] disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
          </button>
          <button
            onClick={() => setCurrentIndex(currentIndex + 1)}
            disabled={!canNext}
            className="p-1 rounded bg-[#2a2d3a] hover:bg-[#3a3d4a] disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </button>
        </div>
      </div>

      {/* Price chart with entry/exit/stop loss */}
      {chartData.length > 0 && (
        <div className="mb-4 bg-[#0f1117] rounded-lg p-2">
          <ResponsiveContainer width="100%" height={120}>
            <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <YAxis
                domain={["auto", "auto"]}
                hide
                padding={{ top: 10, bottom: 10 }}
              />
              <XAxis dataKey="idx" hide />
              <Tooltip
                contentStyle={{
                  background: "#1a1d27",
                  border: "1px solid #2a2d3a",
                  borderRadius: 6,
                  fontSize: 11
                }}
                formatter={(v: number) => [`$${v.toFixed(2)}`, "Price"]}
                labelFormatter={() => ""}
              />
              {/* Entry price line */}
              <ReferenceLine
                y={openTrade.price}
                stroke="#10b981"
                strokeDasharray="4 4"
                strokeWidth={1.5}
              />
              {/* Exit price line */}
              {pair.close && (
                <ReferenceLine
                  y={pair.close.price}
                  stroke="#f43f5e"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                />
              )}
              {/* Stop loss line */}
              {stopLossPrice && (
                <ReferenceLine
                  y={stopLossPrice}
                  stroke="#f59e0b"
                  strokeDasharray="2 2"
                  strokeWidth={1}
                />
              )}
              {/* Support line */}
              {openTrade.support && (
                <ReferenceLine
                  y={openTrade.support}
                  stroke="#10b981"
                  strokeOpacity={0.3}
                  strokeWidth={1}
                />
              )}
              {/* Resistance line */}
              {openTrade.resistance && (
                <ReferenceLine
                  y={openTrade.resistance}
                  stroke="#f43f5e"
                  strokeOpacity={0.3}
                  strokeWidth={1}
                />
              )}
              <Area
                type="monotone"
                dataKey="price"
                stroke="#6366f1"
                strokeWidth={1.5}
                fill="url(#priceGrad)"
                dot={false}
              />
            </AreaChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-4 mt-1 text-[10px]">
            <span className="text-emerald-400">● Entry ${openTrade.price.toFixed(2)}</span>
            {pair.close && <span className="text-rose-400">● Exit ${pair.close.price.toFixed(2)}</span>}
            {stopLossPrice && <span className="text-amber-400">● SL ${stopLossPrice.toFixed(2)}</span>}
          </div>
        </div>
      )}

      {/* Trade panels */}
      <div className="flex gap-3">
        <TradePanel trade={pair.open} label="Entry" />
        {pair.close ? (
          <TradePanel trade={pair.close} label="Exit" />
        ) : (
          <div className="bg-[#0f1117] rounded-lg p-3 flex-1 flex items-center justify-center">
            <span className="text-xs text-amber-400 uppercase">Position Open</span>
          </div>
        )}
      </div>

      {/* P&L summary */}
      {pair.close?.pnl !== undefined && (
        <div className={`mt-3 text-center py-2 rounded-lg ${
          pair.close.pnl >= 0 ? "bg-green-500/10" : "bg-red-500/10"
        }`}>
          <span className={`text-sm font-bold ${
            pair.close.pnl >= 0 ? "text-green-400" : "text-red-400"
          }`}>
            {pair.close.pnl >= 0 ? "+" : ""}${pair.close.pnl.toFixed(2)}
          </span>
          <span className="text-gray-500 text-xs ml-2">
            ({((pair.close.price - pair.open.price) / pair.open.price * 100 * (pair.open.side === "long" ? 1 : -1)).toFixed(2)}%)
          </span>
        </div>
      )}
    </div>
  );
}
