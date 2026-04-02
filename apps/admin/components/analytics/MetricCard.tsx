import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string | number;
  change?: number;
  icon?: LucideIcon;
}

export function MetricCard({ label, value, change, icon: Icon }: MetricCardProps) {
  const isPositive = change !== undefined && change > 0;
  const isNegative = change !== undefined && change < 0;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-zinc-500">{label}</p>
        {Icon && <Icon className="h-5 w-5 text-zinc-400" />}
      </div>
      <p className="mt-2 text-2xl font-bold text-zinc-900">
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
      {change !== undefined && (
        <div className="mt-1 flex items-center gap-1">
          {isPositive && <TrendingUp className="h-4 w-4 text-green-600" />}
          {isNegative && <TrendingDown className="h-4 w-4 text-red-600" />}
          {!isPositive && !isNegative && (
            <Minus className="h-4 w-4 text-zinc-400" />
          )}
          <span
            className={`text-xs font-medium ${
              isPositive
                ? "text-green-600"
                : isNegative
                  ? "text-red-600"
                  : "text-zinc-400"
            }`}
          >
            {isPositive && "+"}
            {change.toFixed(1)}%
          </span>
          <span className="text-xs text-zinc-400">较上期</span>
        </div>
      )}
    </div>
  );
}
