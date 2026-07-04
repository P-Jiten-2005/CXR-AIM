"use client";

import React, { useEffect } from "react";
import { CircleCheck, AlertTriangle, Camera, Info } from "lucide-react";

export type ToastVariant = "success" | "error" | "capture" | "info";

export interface ToastItem {
  id: number;
  variant: ToastVariant;
  title: string;
  message?: string;
}

const VARIANT_STYLE: Record<ToastVariant, { color: string; bg: string; Icon: React.ElementType }> = {
  success: { color: "#10b981", bg: "rgba(16, 185, 129, 0.12)", Icon: CircleCheck },
  error: { color: "#ef4444", bg: "rgba(239, 68, 68, 0.12)", Icon: AlertTriangle },
  capture: { color: "#3b82f6", bg: "rgba(59, 130, 246, 0.12)", Icon: Camera },
  info: { color: "#f59e0b", bg: "rgba(245, 158, 11, 0.12)", Icon: Info },
};

function Toast({ item, onDone }: { item: ToastItem; onDone: (id: number) => void }) {
  useEffect(() => {
    const t = setTimeout(() => onDone(item.id), 3800);
    return () => clearTimeout(t);
  }, [item.id, onDone]);

  const { color, bg, Icon } = VARIANT_STYLE[item.variant];

  return (
    <div
      role="status"
      style={{
        display: "flex", alignItems: "center", gap: "12px",
        minWidth: "280px", maxWidth: "380px", padding: "14px 16px", borderRadius: "12px",
        background: "rgba(13, 18, 28, 0.92)", border: `1px solid ${color}`,
        boxShadow: `0 0 22px ${bg}, 0 8px 24px rgba(0,0,0,0.45)`,
        backdropFilter: "blur(8px)", animation: "cxrToastIn 0.28s cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      <div style={{ flexShrink: 0, width: "36px", height: "36px", borderRadius: "9px",
        display: "flex", alignItems: "center", justifyContent: "center", background: bg }}>
        <Icon size={20} color={color} />
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
        <span style={{ fontSize: "13px", fontWeight: 700, color: "#f3f4f6", letterSpacing: "0.02em" }}>{item.title}</span>
        {item.message && <span style={{ fontSize: "12px", color: "rgba(243, 244, 246, 0.7)" }}>{item.message}</span>}
      </div>
    </div>
  );
}

export default function ToastHost({ toasts, onDone }: { toasts: ToastItem[]; onDone: (id: number) => void }) {
  return (
    <>
      <style>{`@keyframes cxrToastIn { from { opacity: 0; transform: translateX(40px) scale(0.96); } to { opacity: 1; transform: translateX(0) scale(1); } }`}</style>
      <div style={{ position: "fixed", top: "20px", right: "20px", zIndex: 9999,
        display: "flex", flexDirection: "column", gap: "10px", pointerEvents: "none" }}>
        {toasts.map((t) => <Toast key={t.id} item={t} onDone={onDone} />)}
      </div>
    </>
  );
}
