import { api } from "../api/workbench.js";
import { empty, pageHeading, section } from "../components/common/panel.js";
import { status } from "../components/common/status.js";
import { table } from "../components/common/table.js";
import { poll } from "../hooks/poll.js";
import { ItemStates } from "../constants/states.js";
import { el } from "../utils/dom.js";
import { time } from "../utils/format.js";

function progress(run) {
  const total = run.total ?? 0;
  const checked = run.checked ?? 0;
  const bar = el("progress", {max: total || 1, value: checked, "aria-label": "已核车辆数"});
  return el("p", {"data-testid": "run-progress"},
    el("strong", {}, `${checked} / ${total}`), " 辆已核完", total ? [" · ", bar] : null);
}

function reportState(run) {
  const open = run.status === "queued" || run.status === "running";
  return el("div", {class: "stack", id: "run-state"}, status(run.status), progress(run),
    el("p", {}, run.status === "failed" ? run.failure :
      open ? "后台逐车筛查中，已核完的车辆不会因中断而重查。" : run.result?.summary),
    run.status === "done" ? el("a", {class: "button", href: `#evidence/${run.id}`}, "查看业务证据") : null);
}

function vehicleTable(items) {
  if (!items.length) return empty("批次已提交，正在登记车辆。");
  return table(["车辆顺序", "车辆", "筛查状态", "当前结果"],
    items.map(item => [item.position, item.asset, status(item.status, ItemStates),
      item.result ? item.result["放行决定"] : item.failure || "—"]), "逐车筛查进度");
}

export async function runsPage(config, route, signal) {
  const batches = await api.runs();
  const latest = route.id ? await api.run(route.id, signal) : batches[0];
  const detail = latest ? reportState(latest) : empty("进入资料页，选用一个业务样本并提交执行。");
  const vehicles = el("div", {id: "run-vehicles"});
  if (latest) vehicles.replaceChildren(await vehicleTable(await api.runItems(latest.id, signal)));
  async function refresh() {
    try {
      const next = await api.run(latest.id, signal);
      const rows = await api.runItems(latest.id, signal);
      if (signal.aborted) return false;
      detail.replaceChildren(...reportState(next).childNodes);
      vehicles.replaceChildren(await vehicleTable(rows));
      const badge = document.querySelector(`.status-slot[data-run="${next.id}"]`);
      if (badge) badge.replaceChildren(status(next.status));
      const count = document.querySelector(`[data-checked="${next.id}"]`);
      if (count) count.textContent = `${next.checked ?? 0} / ${next.total ?? 0}`;
      return next.status === "queued" || next.status === "running";
    } catch (error) {
      if (!signal.aborted) detail.append(el("p", {role: "alert"}, error.message));
      return false;
    }
  }
  if (latest && (latest.status === "queued" || latest.status === "running")) poll(refresh, signal);
  return el("div", {class: "page"},
    pageHeading(config.modules[2], config.parameter_label),
    latest ? section(latest.case_title, detail, vehicles) : detail,
    section("执行批次", batches.length ? table(["资料", "编号", "参数", "已核车辆数", "状态", "提交时间"],
      batches.map(run => [el("a", {"data-run": run.id, href: `#runs/${run.id}`}, run.case_title), run.id,
        run.parameter, el("span", {"data-checked": run.id}, `${run.checked ?? 0} / ${run.total ?? 0}`),
        el("span", {class: "status-slot", "data-run": run.id}, status(run.status)),
        time(run.created_at)]), "执行批次") :
      empty("暂无执行记录。")));
}
