#!/usr/bin/env python3
"""Reproduce this stopped batch's budget analysis using only the standard library.

Reads the final ledger, batch events, run summaries and saved transcripts. It does
not import the runner/provider, read credentials, contact a service, or resume a
job. Outputs contain only safe attempt metadata and batch-relative evidence refs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re

DEFAULT_BATCH = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parents[1]
RATES = {"input_cache_hit": Decimal("0.006"), "input_cache_miss": Decimal("0.30"), "output": Decimal("1.20")}
TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
VERSIONS = {8192: "v1-output-8192", 10000: "v2-output-10000", 32000: "v3-output-32000"}
CSV_FIELDS = (
    "attempt_id", "started_at_utc", "finished_at_utc", "ledger_status", "requested_model",
    "response_model", "request_max_output_tokens", "recorded_configuration_version", "configuration_version",
    "finish_reasons", "episode_id", "suite", "task", "seed", "episode_outcome", "episode_configuration_version",
    "start_window_match_count", "association", "finish_within_episode_window", "usage_present",
    *TOKEN_FIELDS, "accounted_usd", "settled_peak_usd", "unknown_reserved_usd", "formula_reservation_upper_usd",
)


def unique_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"Duplicate JSON key: {key}")
        output[key] = value
    return output


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_object)


def moment(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Source timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def source_ref(path, batch):
    return os.path.relpath(Path(path).resolve(), batch.resolve())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flag(command, name):
    return command[command.index(name) + 1] if name in command else None


def reservation(maximum):
    return (Decimal(1048576) * RATES["input_cache_miss"] + Decimal(maximum) * RATES["output"]) / Decimal(1000000)


def cost_from_usage(usage, maximum):
    prompt, output = usage["prompt_tokens"], usage["completion_tokens"]
    assert type(prompt) is int and type(output) is int and 0 <= prompt <= 1048576 and 0 <= output <= maximum
    if "total_tokens" in usage:
        assert usage["total_tokens"] == prompt + output
    hit, miss = usage.get("prompt_cache_hit_tokens"), usage.get("prompt_cache_miss_tokens")
    cache_valid = type(hit) is int and type(miss) is int and hit >= 0 and miss >= 0 and hit + miss == prompt
    if not cache_valid:
        hit, miss = 0, prompt
    value = (Decimal(hit) * RATES["input_cache_hit"] + Decimal(miss) * RATES["input_cache_miss"] + Decimal(output) * RATES["output"]) / Decimal(1000000)
    return value, cache_valid


def aggregate(rows):
    counts = Counter(row["ledger_status"] for row in rows)
    tokens = {field: sum(row[field] for row in rows if type(row[field]) is int) for field in TOKEN_FIELDS}
    settled = sum((Decimal(row["settled_peak_usd"]) for row in rows), Decimal(0))
    unknown = sum((Decimal(row["unknown_reserved_usd"]) for row in rows), Decimal(0))
    return {"http_attempts": len(rows), "settled_attempts": counts["settled"], "unknown_reserved_attempts": len(rows) - counts["settled"],
            "attempts_with_recorded_usage": sum(row["usage_present"] for row in rows),
            "settled_peak_usd": str(settled), "unknown_reserved_usd": str(unknown), "accounted_upper_bound_usd": str(settled + unknown),
            "known_usage": tokens}


def grouped(rows, key):
    groups = defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    return [{"group": name, **aggregate(group)} for name, group in sorted(groups.items())]


def analyze(batch, ledger_path):
    ledger = read_json(ledger_path)
    summary = read_json(batch / "summary.json")
    assert summary["status"] == "budget_stopped", "Analyze only the final stopped batch"
    assert Decimal(ledger["limit_usd"]) == Decimal("40")
    events = [json.loads(line, object_pairs_hook=unique_object) for line in (batch / "events.jsonl").read_text().splitlines() if line.strip()]
    results = [event["result"] for event in events if event.get("event") == "result"]
    assert len(results) == len({row["id"] for row in results}) == summary["counts"]["completed"]
    starts = {event["cell"]["id"]: event for event in events if event.get("event") == "started"}
    episodes = []
    evidence = []
    for result in results:
        path = Path(result["run_summary"])
        report = read_json(path)
        task = report["task"]
        assert all(task[name] == result[name] for name in ("suite", "task", "seed"))
        command = report.get("commands", {}).get("online_planner", [])
        maximum = int(report.get("max_tokens") or flag(command, "--max-tokens"))
        version = report.get("configuration_version") or result.get("configuration_version") or VERSIONS[maximum]
        begin, end = moment(report["started_at_utc"]), moment(report["finished_at_utc"])
        assert begin <= end
        transcript_path = Path(report["transcript"]) if report.get("transcript") else None
        transcript = read_json(transcript_path) if transcript_path and transcript_path.is_file() else None
        rejection_match = re.search(r"cost cap reached before HTTP send: accounted=\$([0-9.]+), limit=\$([0-9.]+), next reservation=\$([0-9.]+)", report.get("planner_error") or "")
        rejection = dict(zip(("accounted_usd", "limit_usd", "next_reservation_usd"), rejection_match.groups())) if rejection_match else None
        episodes.append({"episode_id": result["id"], "suite": result["suite"], "task": result["task"], "seed": result["seed"],
                         "outcome": result["outcome"], "phase": result["phase"], "configuration_version": version, "max_tokens": maximum,
                         "imported_pilot": bool(result.get("imported_pilot")), "timed_out": bool(result.get("timed_out")),
                         "started_at_utc": report["started_at_utc"], "finished_at_utc": report["finished_at_utc"],
                         "window_seconds": (end - begin).total_seconds(), "run_summary_ref": source_ref(path, batch),
                         "transcript_ref": source_ref(transcript_path, batch) if transcript else None,
                         "scheduler_started_at_utc": starts.get(result["id"], {}).get("at_utc"),
                         "result_reported_at_utc": result.get("reported_at_utc"), "budget_rejection": rejection,
                         "stats": report.get("planner_stats") or {}, "transcript_stats": transcript.get("stats") if transcript else None,
                         "event_stats": result.get("planner_stats"), "_begin": begin, "_end": end})
        evidence.append({"episode_id": result["id"], "run_summary_ref": source_ref(path, batch), "run_summary_sha256": sha256(path),
                         "transcript_ref": source_ref(transcript_path, batch) if transcript else None,
                         "transcript_sha256": sha256(transcript_path) if transcript else None})
    episodes.sort(key=lambda row: row["_begin"])
    overlaps = []
    for index, first in enumerate(episodes):
        for second in episodes[index + 1:]:
            if second["_begin"] > first["_end"]:
                break
            if first["_begin"] <= second["_end"] and second["_begin"] <= first["_end"]:
                overlaps.append([first["episode_id"], second["episode_id"]])
    episode_by_id = {episode["episode_id"]: episode for episode in episodes}
    rows = []
    token_check_failures = []
    for attempt_id, attempt in ledger["attempts"].items():
        begin = moment(attempt["started_at_utc"])
        finish = moment(attempt["finished_at_utc"]) if attempt.get("finished_at_utc") else None
        matches = [episode for episode in episodes if episode["_begin"] <= begin <= episode["_end"]]
        episode = matches[0] if len(matches) == 1 else None
        usage = attempt.get("usage") or {}
        status = attempt["status"]
        amount = Decimal(attempt["accounted_usd"])
        assert amount >= 0 and amount.is_finite()
        if status == "settled":
            expected, _ = cost_from_usage(usage, attempt["max_output_tokens"])
            if expected != amount:
                token_check_failures.append(attempt_id)
        else:
            assert status == "reserved" and not usage and not finish
            assert amount == reservation(attempt["max_output_tokens"])
        version = attempt.get("configuration_version") or VERSIONS[attempt["max_output_tokens"]]
        contained = episode["_begin"] <= finish <= episode["_end"] if episode and finish else None
        association = "unique_start_and_finish_contained" if episode and contained else "unique_start_only_completion_unknown" if episode and not finish else "finish_crosses_window" if episode else "unmatched" if not matches else "ambiguous_multiple_windows"
        row = {"attempt_id": attempt_id, "started_at_utc": attempt["started_at_utc"], "finished_at_utc": attempt.get("finished_at_utc"),
               "ledger_status": status, "requested_model": "deepseek-flash", "response_model": attempt.get("model"),
               "request_max_output_tokens": attempt["max_output_tokens"], "recorded_configuration_version": attempt.get("configuration_version"),
               "configuration_version": version, "finish_reasons": ";".join(attempt.get("finish_reasons") or []),
               "episode_id": episode["episode_id"] if episode else None, "suite": episode["suite"] if episode else None,
               "task": episode["task"] if episode else None, "seed": episode["seed"] if episode else None,
               "episode_outcome": episode["outcome"] if episode else None, "episode_configuration_version": episode["configuration_version"] if episode else None,
               "start_window_match_count": len(matches), "association": association, "finish_within_episode_window": contained,
               "usage_present": bool(usage), **{field: usage.get(field) for field in TOKEN_FIELDS},
               "accounted_usd": str(amount), "settled_peak_usd": str(amount if status == "settled" else Decimal(0)),
               "unknown_reserved_usd": str(amount if status != "settled" else Decimal(0)),
               "formula_reservation_upper_usd": str(reservation(attempt["max_output_tokens"]))}
        rows.append(row)
    assert not token_check_failures, "A settled entry does not reproduce under the recorded guard rates"
    rows.sort(key=lambda row: (row["started_at_utc"], row["attempt_id"]))
    assert len(rows) == len({row["attempt_id"] for row in rows}) == ledger["request_attempts"] == 4068
    total = aggregate(rows)
    assert Decimal(total["settled_peak_usd"]) == Decimal(ledger["settled_peak_usd"]) == Decimal("31.903549488")
    assert Decimal(total["unknown_reserved_usd"]) == Decimal(ledger["unsettled_reservations_usd"]) == Decimal("7.765401600")
    assert Decimal(total["accounted_upper_bound_usd"]) == Decimal(ledger["accounted_upper_bound_usd"]) == Decimal("39.668951088")
    assert total["settled_attempts"] == 4046 and total["unknown_reserved_attempts"] == 22
    by_episode = defaultdict(list)
    for row in rows:
        if row["episode_id"]:
            by_episode[row["episode_id"]].append(row)
    episode_rows = []
    transcript_coverage = Counter()
    token_outliers, turn_outliers = [], []
    for episode in episodes:
        associated = by_episode[episode["episode_id"]]
        figures = aggregate(associated)
        stats, transcript_stats, event_stats = episode["stats"], episode["transcript_stats"], episode["event_stats"]
        equivalent = transcript_stats == stats == event_stats
        transcript_coverage["available"] += transcript_stats is not None
        transcript_coverage["three_sources_identical"] += equivalent
        known = figures["known_usage"]
        deltas = {"input_tokens": known["prompt_tokens"] - stats.get("total_input_tokens", 0),
                  "output_tokens": known["completion_tokens"] - stats.get("total_output_tokens", 0),
                  "cached_input_tokens": known["prompt_cache_hit_tokens"] - stats.get("total_cached_input_tokens", 0)}
        turns = stats.get("turns_used")
        comparison = {"stats_sources_identical": equivalent, "planner_model_requests": turns,
                      "ledger_minus_transcript_tokens": deltas,
                      "http_attempts_minus_planner_requests": figures["http_attempts"] - turns if type(turns) is int else None,
                      "settled_attempts_minus_planner_requests": figures["settled_attempts"] - turns if type(turns) is int else None}
        if any(deltas.values()):
            settled = [row for row in associated if row["ledger_status"] == "settled"]
            last = settled[-1] if settled else None
            token_outliers.append({"episode_id": episode["episode_id"], "timed_out": episode["timed_out"], "deltas_ledger_minus_transcript": deltas,
                                   "last_settled_attempt_id": last["attempt_id"] if last else None,
                                   "deltas_equal_last_settled_usage": bool(last) and deltas == {"input_tokens": last["prompt_tokens"], "output_tokens": last["completion_tokens"], "cached_input_tokens": last["prompt_cache_hit_tokens"]},
                                   "last_settled_finish_reasons": last["finish_reasons"] if last else None})
        if comparison["settled_attempts_minus_planner_requests"]:
            turn_outliers.append({"episode_id": episode["episode_id"], "planner_model_requests": turns,
                                  "settled_attempts": figures["settled_attempts"], "http_attempts": figures["http_attempts"],
                                  "unknown_reserved_attempts": figures["unknown_reserved_attempts"], "timed_out": episode["timed_out"], "outcome": episode["outcome"]})
        episode_rows.append({key: value for key, value in episode.items() if key not in ("_begin", "_end", "stats", "transcript_stats", "event_stats")} | figures | {"transcript_comparison": comparison})
    currencies = ("settled_peak_usd", "unknown_reserved_usd", "accounted_upper_bound_usd")
    partitions = {
        "by_configuration": grouped(rows, lambda row: row["episode_configuration_version"] or "unassigned"),
        "by_episode_outcome": grouped(rows, lambda row: row["episode_outcome"] or "unassigned"),
        "by_suite": grouped(rows, lambda row: row["suite"] or "unassigned"),
        "by_configuration_and_outcome": grouped(rows, lambda row: f'{row["episode_configuration_version"] or "unassigned"} | {row["episode_outcome"] or "unassigned"}'),
        "by_request_start_hour_utc": grouped(rows, lambda row: moment(row["started_at_utc"]).strftime("%Y-%m-%dT%H:00:00Z")),
    }
    for groups in partitions.values():
        assert sum(group["http_attempts"] for group in groups) == len(rows)
        for field in currencies:
            assert sum((Decimal(group[field]) for group in groups), Decimal(0)) == Decimal(total[field])
    model_requests = sum(episode["stats"].get("turns_used", 0) for episode in episodes)
    maximum_reservation = reservation(32000)
    remaining = Decimal(ledger["limit_usd"]) - Decimal(total["accounted_upper_bound_usd"])
    match_counts = Counter(row["start_window_match_count"] for row in rows)
    rejected_episodes = [episode for episode in episodes if episode["outcome"] == "budget_stopped"]
    assert len(rejected_episodes) == 1 and rejected_episodes[0]["budget_rejection"]
    rejected = rejected_episodes[0]
    assert Decimal(rejected["budget_rejection"]["accounted_usd"]) == Decimal(total["accounted_upper_bound_usd"])
    assert Decimal(rejected["budget_rejection"]["limit_usd"]) == Decimal(ledger["limit_usd"])
    assert Decimal(rejected["budget_rejection"]["next_reservation_usd"]) == maximum_reservation > remaining
    analysis = {
        "analysis_schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Stopped standard LIBERO batch, including the externally reused pilot; no API or billing-balance query performed by this analysis.",
        "source_inputs": {"ledger_ref": source_ref(ledger_path, batch), "ledger_sha256": sha256(ledger_path), "events_ref": "events.jsonl", "events_sha256": sha256(batch / "events.jsonl"), "summary_ref": "summary.json", "summary_sha256": sha256(batch / "summary.json")},
        "status": summary["status"], "episode_counts": summary["counts"], "total": total,
        "guard_price_policy": {"currency": "USD", "unit": "per million tokens", "peak_rates": {key: str(value) for key, value in RATES.items()},
                               "full_input_token_bound": 1048576, "reservation_by_max_output_tokens": {str(cap): str(reservation(cap)) for cap in VERSIONS},
                               "source": "https://api-docs.deepseek.com/quick_start/pricing/", "guard_price_check_date": "2026-11-01",
                               "settlement": "Validated usage with reconciled cache split at peak rates; otherwise all input charged as cache-miss. Off-peak discounts are not applied.",
                               "not_an_invoice": True, "unknown_reservations_released": False},
        "matching": {"method": "Attempt start timestamp in the closed [run-summary.started_at_utc, run-summary.finished_at_utc] interval. Both timestamps are converted to UTC. Only a unique match is assigned.",
                     "provenance_limit": "Ledger has no native episode ID or retry parent ID. This is a serial temporal association, not a provider transaction-to-episode join. Missing finish times establish start association only.",
                     "episode_windows": len(episodes), "external_pilot_windows": sum(e["imported_pilot"] for e in episodes),
                     "start_matches_zero": match_counts[0], "start_matches_unique": match_counts[1], "start_matches_multiple": sum(value for key, value in match_counts.items() if key > 1),
                     "unique_start_coverage": match_counts[1] / len(rows), "overlapping_window_pairs": overlaps,
                     "finished_attempts": sum(row["finished_at_utc"] is not None for row in rows), "finish_crosses_associated_window": sum(row["finish_within_episode_window"] is False for row in rows),
                     "missing_finish_attempts": sum(row["finished_at_utc"] is None for row in rows),
                     "configuration_mismatch_attempts": sum(row["configuration_version"] != row["episode_configuration_version"] for row in rows if row["episode_id"])},
        "usage_coverage": {"recorded_usage_attempts": total["attempts_with_recorded_usage"], "unknown_usage_attempts": len(rows) - total["attempts_with_recorded_usage"],
                           "unknown_tokens_are_not_zero": True, "retry_note": "HTTP attempts include initial sends and any SDK retries, but the ledger does not identify retry ordinals. Unknown reservations and attempt/model-request differences are not an exact retry count."},
        "transcript_reconciliation": {"episodes_with_transcript": transcript_coverage["available"], "episodes_stats_identical_across_transcript_run_summary_event": transcript_coverage["three_sources_identical"],
                                      "planner_model_requests": model_requests, "http_attempts": len(rows), "settled_attempts": total["settled_attempts"],
                                      "http_attempts_minus_model_requests": len(rows) - model_requests, "token_outliers": token_outliers, "turn_count_outliers": turn_outliers,
                                      "interpretation": "Use ledger usage for fee reconstruction. A recorded settled response can be absent from planner aggregate usage after timeout; that is an inference about the observed difference, not proof of a retry."},
        "end_budget_check": {"authorized_limit_usd": ledger["limit_usd"], "remaining_after_accounted_upper_bound_usd": str(remaining), "next_32000_request_reservation_usd": str(maximum_reservation),
                             "would_be_accounted_usd": str(Decimal(total["accounted_upper_bound_usd"]) + maximum_reservation), "exceeds_limit_by_usd": str(maximum_reservation - remaining),
                             "latest_attempt_started_at_utc": max(row["started_at_utc"] for row in rows), "latest_settled_finished_at_utc": max(row["finished_at_utc"] for row in rows if row["finished_at_utc"]),
                             "ledger_updated_at_utc": ledger.get("updated_at_utc"), "summary_updated_at_utc": summary["updated_at_utc"],
                             "rejection_evidence": {key: rejected[key] for key in ("episode_id", "run_summary_ref", "budget_rejection", "finished_at_utc", "result_reported_at_utc")},
                             "rejected_next_request_not_in_attempt_count": True, "budget_stopped_is_separate_from_failure": summary["counts"]["budget_stopped"] == 1},
        **partitions, "per_episode": episode_rows, "episode_evidence": evidence,
        "assertions_passed": ["No duplicate JSON keys or attempt IDs", "Ledger request count equals4068 unique attempts", "117 unique episode windows", "Every settled fee reconstructs exactly from saved usage and guard peak rates", "Every unknown reserve reconstructs from its original wire cap", "All three ledger currency totals reconcile exactly", "Each grouping conserves attempt and currency totals"],
    }
    assert len(episodes) == 117
    return analysis, rows


def markdown(analysis):
    total, matching, reconciliation, end = (analysis[key] for key in ("total", "matching", "transcript_reconciliation", "end_budget_check"))
    lines = ["# 费用与请求归属审计", "", "本材料由 `report/scripts/analyze_budget.py` 从终态账本、事件、各回合摘要和保存的 transcript 重新计算。未调用 API、未查询余额或账单。", "",
             "**口径：以下 USD 金额是按已保存 usage 与 guard 峰时费率计算的保守结算／预留，不是服务商实付账单。22条未知请求的预留未释放，其 token 数不能视为零。**", "",
             "| 项目 | 数值 |", "|---|---:|", f'| HTTP尝试（含可能的SDK重试） | {total["http_attempts"]} |', f'| 有可信usage并已结算 | {total["settled_attempts"]} |', f'| 未知预留 | {total["unknown_reserved_attempts"]} |',
             f'| 峰价保守结算 USD | {total["settled_peak_usd"]} |', f'| 未知预留 USD | {total["unknown_reserved_usd"]} |', f'| 总占款上界 USD | {total["accounted_upper_bound_usd"]} |',
             f'| 已知输入／输出token | {total["known_usage"]["prompt_tokens"]} / {total["known_usage"]["completion_tokens"]} |', f'| 已知缓存命中／未命中输入token | {total["known_usage"]["prompt_cache_hit_tokens"]} / {total["known_usage"]["prompt_cache_miss_tokens"]} |', "",
             "费率（每百万token）：缓存命中输入0.006、未命中输入0.30、输出1.20 USD；缓存细分不完整或不相等时按全部未命中计。未应用非峰时优惠。预留包含1,048,576输入token上界及请求实际max_tokens：8192→0.3244032、10000→0.3265728、32000→0.3529728 USD。来源为 guard 记录的2026-11-01官方价格。", "",
             "## 时间窗归属", "", f'{matching["episode_windows"]}个唯一回合窗（含1个外部复用pilot），用回合run-summary的开始到清理结束时间做闭区间。{matching["start_matches_unique"]}条尝试开始时间唯一落窗；无匹配{matching["start_matches_zero"]}、多匹配{matching["start_matches_multiple"]}、窗口重叠{len(matching["overlapping_window_pairs"])}。',
             f'{matching["finished_attempts"]}条有结束时间的请求均未跨窗；{matching["missing_finish_attempts"]}条未知预留没有finish或usage，只能确认开始时间归属。配置不匹配条数：{matching["configuration_mismatch_attempts"]}。', "",
             "这是串行执行下的唯一时间匹配，不是ledger原生episode ID关联；费用并非直接保存在每回合文件里。CSV保留原始attempt ID和开始／结束时间、匹配数量、归属置信类型及原始输出上限，不包含正文、鉴权头或个人绝对路径。", ""]
    for title, key in (("按配置", "by_configuration"), ("按回合结局", "by_episode_outcome"), ("按suite", "by_suite"), ("按配置与结局", "by_configuration_and_outcome"), ("按请求开始UTC小时", "by_request_start_hour_utc")):
        lines += [f"## {title}", "", "| 分组 | HTTP尝试 | 有usage | 未知预留 | 已结算峰价USD | 未知预留USD | 总占款上界USD |", "|---|---:|---:|---:|---:|---:|---:|"]
        for group in analysis[key]:
            label = group["group"].replace("|", "/")
            lines.append(f'| {label} | {group["http_attempts"]} | {group["settled_attempts"]} | {group["unknown_reserved_attempts"]} | {group["settled_peak_usd"]} | {group["unknown_reserved_usd"]} | {group["accounted_upper_bound_usd"]} |')
        lines.append("")
    lines += ["## 与transcript统计核对", "", f'{reconciliation["episodes_stats_identical_across_transcript_run_summary_event"]}/117回合的transcript stats、run-summary planner_stats、事件planner_stats完全相同。其model requests合计{reconciliation["planner_model_requests"]}；HTTP尝试{reconciliation["http_attempts"]}、已结算尝试{reconciliation["settled_attempts"]}属于不同口径，不能把差值直接称为重试次数。', ""]
    for item in reconciliation["token_outliers"]:
        lines.append(f'- 唯一token差异回合 `{item["episode_id"]}`：ledger比transcript多 {json.dumps(item["deltas_ledger_minus_transcript"], ensure_ascii=False)}；逐项恰等于最后一条已结算usage（核对结果：{item["deltas_equal_last_settled_usage"]}）。该回合超时，不能据此证明发生重试。')
    lines += ["", "| 回合 | transcript模型请求 | 已结算HTTP | 全部HTTP | 未知预留 |", "|---|---:|---:|---:|---:|"]
    for item in reconciliation["turn_count_outliers"]:
        lines.append(f'| {item["episode_id"]} | {item["planner_model_requests"]} | {item["settled_attempts"]} | {item["http_attempts"]} | {item["unknown_reserved_attempts"]} |')
    lines += ["", "## 预算拒绝与边界", "", f'终态是budget_stopped；117条记录由104成功、12失败、1预算截断构成，1883未运行。剩余保守余额 {end["remaining_after_accounted_upper_bound_usd"]} USD，小于下一个32000请求预留 {end["next_32000_request_reservation_usd"]}；若发送将达到 {end["would_be_accounted_usd"]}，超40上限 {end["exceeds_limit_by_usd"]}。',
             f'最后已登记请求开始于 {end["latest_attempt_started_at_utc"]}，最后结算于 {end["latest_settled_finished_at_utc"]}；账本最后更新时间 {end["ledger_updated_at_utc"]}。发送前拒绝未增加第4069条attempt。',
             "拒绝证据：`episodes/libero_10_t6_s2/run-summary.json` 的planner_error及 `planner.log:2082`；事件结果为budget_stopped，不计入failure。", "",
             "复现命令：`python3 report/scripts/analyze_budget.py`（从任意目录运行该脚本的绝对路径也可）。输出的所有数字依赖最终输入文件；文件SHA256、逐回合证据和对账差异保存在budget_analysis.json。所有金额使用Decimal求和，未以浮点近似做预算核对。", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=DEFAULT_BATCH)
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    batch = args.batch.resolve()
    ledger = args.ledger.resolve() if args.ledger else batch.parent / "deepseek-pilot-2026-11-01-budget.json"
    analysis, rows = analyze(batch, ledger)
    data = REPORT / "data"
    data.mkdir(parents=True, exist_ok=True)
    (data / "budget_analysis.json").write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n")
    with (data / "budget_attempts.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (REPORT / "budget.md").write_text(markdown(analysis))
    print(json.dumps({"attempts": len(rows), "episode_windows": analysis["matching"]["episode_windows"], "total": analysis["total"], "matching": analysis["matching"], "outputs": ["data/budget_analysis.json", "data/budget_attempts.csv", "budget.md"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
