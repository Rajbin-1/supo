"use client";

import { useEffect, useState } from "react";
import { Activity, Cpu, Database, RefreshCw, Zap } from "lucide-react";

interface UsageData {
  gemini: {
    rpm: number;
    max_rpm: number;
    tpm: number;
    max_tpm: number;
    rpd: number;
    max_rpd: number;
    input_tokens_today: number;
    output_tokens_today: number;
    reset_timezone: string;
  };
  assemblyai: {
    used_hours: number;
    max_hours: number;
    offset_hours: number;
    remaining_hours: number;
    total_seconds: number;
  };
}

export function ApiUsageCard() {
  const [data, setData] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchUsage = async () => {
    try {
      setLoading(true);
      const res = await fetch("http://localhost:8000/api/usage");
      if (res.ok) {
        const json = await res.json();
        setData(json);
      }
    } catch {
      // Backend maybe starting up
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsage();
    const interval = setInterval(fetchUsage, 15000);
    return () => clearInterval(interval);
  }, []);

  if (!data) return null;

  const geminiPercent = Math.min(100, Math.round((data.gemini.rpd / (data.gemini.max_rpd || 1)) * 100));
  const aaiPercent = Math.min(100, Math.round((data.assemblyai.used_hours / (data.assemblyai.max_hours || 1)) * 100));

  return (
    <div className="mb-6 rounded-xl border border-border/80 bg-card/60 p-4 shadow-sm backdrop-blur-md">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-emerald-500 animate-pulse" />
          <h2 className="text-xs font-semibold tracking-wider uppercase text-muted-foreground">
            Real-Time API Quotas & Limits
          </h2>
        </div>
        <button
          onClick={fetchUsage}
          disabled={loading}
          title="Refresh Usage"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* Gemini Card */}
        <div className="rounded-lg border border-border/50 bg-background/50 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 font-medium text-foreground">
              <Zap className="h-3.5 w-3.5 text-blue-500" />
              Gemini 3 Flash
            </span>
            <span className="font-mono font-medium text-xs text-muted-foreground">
              {data.gemini.rpd} / {data.gemini.max_rpd} RPD
            </span>
          </div>

          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                geminiPercent > 85 ? "bg-red-500" : geminiPercent > 60 ? "bg-amber-500" : "bg-blue-500"
              }`}
              style={{ width: `${Math.max(3, geminiPercent)}%` }}
            />
          </div>

          <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>RPM: <strong className="text-foreground">{data.gemini.rpm}</strong> / {data.gemini.max_rpm}</span>
            <span>Resets midnight PT</span>
          </div>
        </div>

        {/* AssemblyAI Card */}
        <div className="rounded-lg border border-border/50 bg-background/50 p-3">
          <div className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 font-medium text-foreground">
              <Cpu className="h-3.5 w-3.5 text-purple-500" />
              AssemblyAI
            </span>
            <span className="font-mono font-medium text-xs text-muted-foreground">
              {data.assemblyai.used_hours.toFixed(1)} / {data.assemblyai.max_hours.toFixed(0)} hrs
            </span>
          </div>

          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-secondary">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                aaiPercent > 85 ? "bg-red-500" : aaiPercent > 60 ? "bg-amber-500" : "bg-purple-500"
              }`}
              style={{ width: `${Math.max(3, aaiPercent)}%` }}
            />
          </div>

          <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>Free Tier: <strong>185 hrs</strong></span>
            <span className="font-medium text-emerald-500">{data.assemblyai.remaining_hours.toFixed(1)} hrs left</span>
          </div>
        </div>
      </div>
    </div>
  );
}
