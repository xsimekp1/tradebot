"use client";

import React, { useState, useMemo } from "react";

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
          // Previous trade wasn't closed, add it anyway
          pairs.push({ open: currentOpen });
        }
        currentOpen = trade;
      } else if (trade.action === "close" && currentOpen) {
        pairs.push({ open: currentOpen, close: trade });
        currentOpen = null;
      }
    }
    // Add last open if not closed
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
        {trade.support !== undefined && (
          <div>
            <span className="text-gray-500">Support</span>
            <p className="text-emerald-400 font-medium">${trade.support.toFixed(2)}</p>
          </div>
        )}
        {trade.resistance !== undefined && (
          <div>
            <span className="text-gray-500">Resistance</span>
            <p className="text-rose-400 font-medium">${trade.resistance.toFixed(2)}</p>
          </div>
        )}
        {trade.position_pct !== undefined && (
          <div>
            <span className="text-gray-500">Channel Position</span>
            <p className="text-indigo-400 font-medium">{formatPct(trade.position_pct)}</p>
          </div>
        )}
        {trade.score !== undefined && (
          <div>
            <span className="text-gray-500">Score</span>
            <p className={`font-medium ${trade.score >= 0 ? "text-green-400" : "text-red-400"}`}>
              {trade.score >= 0 ? "+" : ""}{trade.score.toFixed(3)}
            </p>
          </div>
        )}
        {trade.spread !== undefined && (
          <div>
            <span className="text-gray-500">Channel Spread</span>
            <p className="text-gray-300 font-medium">${trade.spread.toFixed(2)}</p>
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

  // Calculate channel visualization for open trade
  const openTrade = pair.open;
  const hasChannel = openTrade.support !== undefined && openTrade.resistance !== undefined;

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

      {/* Channel visualization */}
      {hasChannel && (
        <div className="mb-4 relative h-8 bg-[#0f1117] rounded-lg overflow-hidden">
          {/* Gradient from support to resistance */}
          <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/20 via-gray-500/10 to-rose-500/20" />
          {/* Position marker */}
          {openTrade.position_pct !== undefined && (
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-indigo-400"
              style={{ left: `${openTrade.position_pct * 100}%` }}
            >
              <div className="absolute -top-0.5 left-1/2 -translate-x-1/2 w-2 h-2 bg-indigo-400 rounded-full" />
            </div>
          )}
          {/* Labels */}
          <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[10px] text-emerald-400 font-medium">
            ${openTrade.support?.toFixed(0)}
          </span>
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-rose-400 font-medium">
            ${openTrade.resistance?.toFixed(0)}
          </span>
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
