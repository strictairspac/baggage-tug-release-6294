export const States = Object.freeze({
  queued: "等待执行", running: "筛查中", done: "已完成", failed: "执行失败",
});

export const ItemStates = Object.freeze({
  queued: "待筛查", processing: "筛查中", done: "已核完", failed: "核查失败",
});

export const Actions = Object.freeze({
  create_case: "登记资料", enqueue: "提交执行", done: "执行完成", failed: "执行失败", review: "复核签署",
});
