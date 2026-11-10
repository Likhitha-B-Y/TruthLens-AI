import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { STATUS_META } from "../lib/format";
import type { Status } from "../lib/types";

export function Donut({ supported, contradicted, insufficient, size = 200, centerLabel }: {
  supported: number; contradicted: number; insufficient: number; size?: number; centerLabel?: string;
}) {
  const total = supported + contradicted + insufficient;
  const data: { key: Status; value: number }[] = [
    { key: "SUPPORTED", value: supported }, { key: "CONTRADICTED", value: contradicted }, { key: "INSUFFICIENT_EVIDENCE", value: insufficient },
  ];
  return (
    <div className="relative mx-auto" style={{ width: size, height: size }} role="img"
      aria-label={`${supported} supported, ${contradicted} contradicted, ${insufficient} insufficient evidence`}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={total ? data : [{ key: "SUPPORTED", value: 1 }]} dataKey="value" innerRadius="68%" outerRadius="100%" paddingAngle={total ? 3 : 0}
            stroke="none" cornerRadius={6} isAnimationActive animationDuration={700}>
            {(total ? data : [{ key: "SUPPORTED" as Status, value: 1 }]).map((d, i) => (
              <Cell key={i} fill={total ? STATUS_META[d.key].hex : "rgb(var(--line))"} />
            ))}
          </Pie>
          {total > 0 && <Tooltip formatter={(v: number, _n, p) => [v, STATUS_META[(p.payload as { key: Status }).key].label]}
            contentStyle={{ borderRadius: 12, border: "1px solid rgb(var(--line))", background: "rgb(var(--surface))", color: "rgb(var(--ink))" }} />}
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
        <div><p className="font-display text-4xl font-semibold leading-none">{total}</p><p className="mt-1 text-xs font-medium text-muted">{centerLabel ?? "claims"}</p></div>
      </div>
    </div>
  );
}

export function Legend({ supported, contradicted, insufficient }: { supported: number; contradicted: number; insufficient: number }) {
  const rows: [Status, number][] = [["SUPPORTED", supported], ["CONTRADICTED", contradicted], ["INSUFFICIENT_EVIDENCE", insufficient]];
  return (
    <ul className="space-y-2.5">
      {rows.map(([k, v]) => (
        <li key={k} className="flex items-center justify-between gap-6 text-sm">
          <span className="flex items-center gap-2.5"><span className="h-2.5 w-2.5 rounded-full" style={{ background: STATUS_META[k].hex }} />{STATUS_META[k].label}</span>
          <b className="tabular-nums">{v}</b>
        </li>
      ))}
    </ul>
  );
}

export function StackedBar({ supported, contradicted, insufficient }: { supported: number; contradicted: number; insufficient: number }) {
  const total = supported + contradicted + insufficient || 1;
  return (
    <div className="flex h-3 overflow-hidden rounded-full bg-sunken" role="img" aria-label="Claim distribution">
      {([["SUPPORTED", supported], ["CONTRADICTED", contradicted], ["INSUFFICIENT_EVIDENCE", insufficient]] as [Status, number][]).map(([k, v]) =>
        v > 0 ? <div key={k} className={STATUS_META[k].bar} style={{ width: `${(v / total) * 100}%` }} title={`${STATUS_META[k].label}: ${v}`} /> : null)}
    </div>
  );
}
