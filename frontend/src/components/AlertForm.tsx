import { useEffect, useState } from "react";
import { api } from "../api";
import type { AlertBasis, AlertDirection } from "../api";

export const BASIS_LABEL: Record<AlertBasis, string> = {
  ABSOLUTE: "절대 목표가", PURCHASE_AVG: "평균매입가 대비",
  WEEK52_HIGH: "52주 고점 대비", WEEK52_LOW: "52주 저점 대비",
  REFERENCE: "변동률 감시",
};

export interface AssetOpt { asset_id: number; label: string; held: boolean; manual: boolean; }

export function basisDisabled(b: AlertBasis, held: boolean, manual: boolean) {
  return (b === "PURCHASE_AVG" && !held) ||
    ((b === "WEEK52_HIGH" || b === "WEEK52_LOW") && manual);
}

interface Props {
  /** 종목 선택형(알림 허브)이면 목록 전달, 상세 페이지면 fixed 전달 */
  options?: AssetOpt[];
  fixed?: { asset_id: number; held: boolean; manual: boolean };
  onAdded: () => void;
}

export default function AlertForm({ options, fixed, onAdded }: Props) {
  const [sel, setSel] = useState<number | "">(fixed ? fixed.asset_id : "");
  const [basis, setBasis] = useState<AlertBasis>("ABSOLUTE");
  const [dir, setDir] = useState<AlertDirection>("ABOVE");
  const [value, setValue] = useState("");
  const [msg, setMsg] = useState("");

  const selectedOpt = fixed ? undefined : options?.find((o) => o.asset_id === sel);
  const cur: { asset_id: number; held: boolean; manual: boolean } | undefined =
    fixed
      ? fixed
      : selectedOpt
        ? { asset_id: selectedOpt.asset_id, held: selectedOpt.held, manual: selectedOpt.manual }
        : undefined;

  useEffect(() => {
    if (cur && basisDisabled(basis, cur.held, cur.manual)) setBasis("ABSOLUTE");
  }, [cur?.asset_id]);

  const unit = basis === "ABSOLUTE" ? "가격" : basis === "REFERENCE" ? "변동 %" : "%";
  const add = async () => {
    if (!cur) { setMsg("종목을 선택하세요"); return; }
    setMsg("");
    try {
      await api.createAlert({
        asset_id: cur.asset_id, basis,
        direction: basis === "REFERENCE" ? "BOTH" : dir,
        value: Number(value),
      });
      setValue(""); onAdded();
    } catch (e: any) { setMsg("추가 실패: " + e.message); }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {options && (
        <select className="input" value={sel}
          onChange={(e) => setSel(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">종목 선택…</option>
          {options.map((o) => <option key={o.asset_id} value={o.asset_id}>{o.label}</option>)}
        </select>
      )}
      <select className="input" value={basis} onChange={(e) => setBasis(e.target.value as AlertBasis)}>
        {(Object.keys(BASIS_LABEL) as AlertBasis[]).map((b) => (
          <option key={b} value={b}
            disabled={!!cur && basisDisabled(b, cur.held, cur.manual)}>{BASIS_LABEL[b]}</option>
        ))}
      </select>
      {basis !== "REFERENCE" && (
        <select className="input" value={dir} onChange={(e) => setDir(e.target.value as AlertDirection)}>
          <option value="ABOVE">이상 도달</option>
          <option value="BELOW">이하 도달</option>
        </select>
      )}
      <input className="input w-28" placeholder={unit} value={value}
        onChange={(e) => setValue(e.target.value)} />
      <span className="text-xs text-muted">{unit}</span>
      <button onClick={add} className="btn btn-primary">추가</button>
      {msg && <span className="text-sm text-muted">{msg}</span>}
    </div>
  );
}
