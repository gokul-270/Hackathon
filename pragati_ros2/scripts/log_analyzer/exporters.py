"""
Export formats for the log analyzer.

Group 18 of the vehicle-log-analyzer change:
  18.1/18.2/18.3 — CSV export (events and metrics)
  18.4/18.5      — HTML report (self-contained, inline CSS)
  18.6/18.7      — Session comparison
  18.8           — --analyze flag (rolling stats for --watch)

All third-party-free: stdlib csv, html, json only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .analyzer import ROS2LogAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten(d: dict, prefix: str = "", sep: str = ".") -> Dict[str, Any]:
    """Recursively flatten a nested dict with dot-notation keys."""
    out: Dict[str, Any] = {}
    for key, val in d.items():
        full_key = f"{prefix}{sep}{key}" if prefix else key
        if isinstance(val, dict):
            out.update(_flatten(val, full_key, sep))
        elif isinstance(val, (list, tuple)):
            out[full_key] = json.dumps(val)
        else:
            out[full_key] = val
    return out


def _write_csv(filepath: Path, rows: List[dict]) -> None:
    """Write a list of dicts as CSV. All stdlib, lazy import."""
    import csv  # noqa: PLC0415

    if not rows:
        filepath.write_text("# No data\n")
        return

    # Collect all keys from all rows for consistent columns
    all_keys: list = []
    seen: set = set()
    for row in rows:
        for k in row:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    with filepath.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# task 18.2 — CSV events export
# ---------------------------------------------------------------------------


def _add_text_pattern_rows(
    rows: List[dict], analyzer: "ROS2LogAnalyzer",
) -> None:
    """task 5.1 — Append text-pattern events to *rows*.

    Includes pick_failures, motor_failure_details, emergency_shutdowns,
    camera_reconnections, arm_status_transitions, and arm_client_mqtt_events
    (communication errors).  Each row uses a consistent column set:
    _ts, _event_type, pattern_name, matched_text, source_file, line_number
    plus any extra fields from the original event dict.
    """

    def _text_row(
        event: dict,
        event_type: str,
        pattern_name: str,
        matched_text: str = "",
    ) -> dict:
        flat = _flatten(event)
        flat["_event_type"] = event_type
        flat["pattern_name"] = pattern_name
        flat["matched_text"] = matched_text
        # source_file / line_number may not exist on text-pattern events;
        # ensure the columns are always present (empty when unknown).
        flat.setdefault("source_file", "")
        flat.setdefault("line_number", "")
        return flat

    for pf in analyzer.events.pick_failures:
        reason = pf.get("reason", "")
        phase = pf.get("phase", "")
        rows.append(_text_row(
            pf, "text_pattern", "pick_failure",
            f"PICK FAILED at {phase}: {reason}",
        ))

    for mf in analyzer.events.motor_failure_details:
        mid = mf.get("motor_id", "")
        err = mf.get("error", "")
        rows.append(_text_row(
            mf, "text_pattern", "motor_failure",
            f"Motor {mid} error={err}",
        ))

    for es in analyzer.events.emergency_shutdowns:
        rows.append(_text_row(
            es, "text_pattern", "emergency_shutdown",
            f"EMERGENCY SHUTDOWN: {es.get('reason', '')}",
        ))

    for cr in analyzer.events.camera_reconnections:
        rows.append(_text_row(
            cr, "text_pattern", "camera_reconnection",
            f"camera {cr.get('type', '')}",
        ))

    for st in analyzer.events.arm_status_transitions:
        rows.append(_text_row(
            st, "text_pattern", "arm_status_transition",
            f"status={st.get('status', '')}",
        ))

    # Communication errors from ARM_client MQTT events
    for me in analyzer.events.arm_client_mqtt_events:
        etype = me.get("event_type", me.get("type", "mqtt_event"))
        rows.append(_text_row(
            me, "text_pattern", "communication_error",
            f"MQTT {etype}",
        ))


def export_csv_events(analyzer: "ROS2LogAnalyzer", output_dir: Path) -> Path:
    """
    Export one row per event, all event types, nested fields flattened.

    task 5.1/5.2 — Merges JSON events and text-pattern events into a
    single chronological stream sorted by timestamp.
    """
    rows: List[dict] = []

    def _add_rows(event_list: List[dict], event_type: str) -> None:
        for e in event_list:
            flat = _flatten(e)
            flat["_event_type"] = event_type
            rows.append(flat)

    # JSON events
    _add_rows(analyzer.events.picks, "pick_complete")
    _add_rows(analyzer.events.cycles, "cycle_complete")
    _add_rows(analyzer.events.state_transitions, "state_transition")
    _add_rows(analyzer.events.drive_commands, "drive_command")
    _add_rows(analyzer.events.steering_commands, "steering_command")
    _add_rows(analyzer.events.steering_settle, "steering_settle")
    _add_rows(analyzer.events.cmd_vel, "cmd_vel_latency")
    _add_rows(analyzer.events.control_loop, "control_loop_health")
    _add_rows(analyzer.events.motor_health_arm, "motor_health_arm")
    _add_rows(analyzer.events.motor_health_vehicle, "motor_health_vehicle")
    _add_rows(analyzer.events.arm_coordination, "arm_coordination")
    _add_rows(analyzer.events.auto_sessions, "auto_mode_session")
    _add_rows(analyzer.events.detection_summaries, "detection_summary")
    _add_rows(analyzer.events.motor_alerts, "motor_alert")
    _add_rows(analyzer.events.startup, "startup_timing")
    _add_rows(analyzer.events.shutdown, "shutdown_timing")

    # task 5.1 — text-pattern events
    _add_text_pattern_rows(rows, analyzer)

    # task 5.2 — chronological sort by timestamp
    rows.sort(key=lambda r: r.get("_ts") or 0)

    out_path = output_dir / "events.csv"
    _write_csv(out_path, rows)
    return out_path


# ---------------------------------------------------------------------------
# task 18.3 — CSV metrics export
# ---------------------------------------------------------------------------


def export_csv_metrics(analyzer: "ROS2LogAnalyzer", output_dir: Path) -> Path:
    """
    Export per-hour computed metrics as CSV.

    Requires field summary to be generated first.
    """
    from .reports import generate_field_summary

    if analyzer.field_summary is None:
        analyzer.field_summary = generate_field_summary(analyzer)

    hourly = analyzer.field_summary.hourly_throughput
    rows = [dict(b) for b in hourly]  # already flat dicts

    out_path = output_dir / "metrics.csv"
    _write_csv(out_path, rows)
    return out_path


# ---------------------------------------------------------------------------
# task 18.5 — HTML report
# ---------------------------------------------------------------------------

_HTML_CSS = """
body { font-family: monospace; background: #1e1e1e; color: #d4d4d4; margin: 2em; }
h1 { color: #4fc1ff; border-bottom: 2px solid #4fc1ff; padding-bottom: 0.3em; }
h2 { color: #9cdcfe; border-left: 4px solid #9cdcfe; padding-left: 0.5em; margin-top: 2em; }
h3 { color: #dcdcaa; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th { background: #2d2d2d; color: #9cdcfe; text-align: left; padding: 6px 12px;
     cursor: pointer; user-select: none; white-space: nowrap; }
th .sort-arrow { margin-left: 4px; font-size: 0.8em; }
td { padding: 4px 12px; border-bottom: 1px solid #333; }
tr:nth-child(even) { background: #252526; }
.ok { color: #4ec9b0; }
.warn { color: #ce9178; }
.error { color: #f14c4c; }
.section { margin: 1.5em 0; background: #252526; padding: 1em; border-radius: 4px; }
.kv { display: grid; grid-template-columns: 300px 1fr; gap: 0.3em; }
.kv span:first-child { color: #9cdcfe; }
ul { margin: 0.5em 0; padding-left: 1.5em; }
li { margin: 0.2em 0; }
.alert { color: #ffcc00; font-weight: bold; }
.section-filter { margin: 0.5em 0; padding: 4px 8px; width: 300px;
     background: #1e1e1e; color: #d4d4d4; border: 1px solid #555;
     border-radius: 3px; font-family: monospace; font-size: 0.9em; }
"""

# ---------------------------------------------------------------------------
# task 5.3 — Inline JavaScript for client-side column sorting
# task 5.4 — Section-level text filter input
# ---------------------------------------------------------------------------

_HTML_JS = """
<script>
(function(){
  /* task 5.3 — sortable table columns */
  function isNumeric(s){
    if(s==='')return false;
    return !isNaN(s.replace(/[%,ms°]/g,''));
  }
  function sortVal(s){
    var n=parseFloat(s.replace(/[%,ms°]/g,''));
    return isNaN(n)?s.toLowerCase():n;
  }
  function sortTable(th){
    var table=th.closest('table');
    if(!table)return;
    var idx=Array.prototype.indexOf.call(th.parentNode.children,th);
    var tbody=table.querySelector('tbody');
    if(!tbody)return;
    var rows=Array.from(tbody.querySelectorAll('tr'));
    if(rows.length===0)return;
    /* detect if column is numeric by sampling first non-empty values */
    var numeric=true;
    for(var i=0;i<Math.min(rows.length,10);i++){
      var c=rows[i].children[idx];
      if(c){var t=c.textContent.trim();if(t!==''&&!isNumeric(t)){numeric=false;break;}}
    }
    var dir=th.getAttribute('data-sort-dir')==='asc'?'desc':'asc';
    /* clear all arrows in this thead */
    var ths=th.parentNode.querySelectorAll('th');
    for(var j=0;j<ths.length;j++){
      ths[j].removeAttribute('data-sort-dir');
      var ar=ths[j].querySelector('.sort-arrow');
      if(ar)ar.textContent='';
    }
    th.setAttribute('data-sort-dir',dir);
    var arrow=th.querySelector('.sort-arrow');
    if(!arrow){arrow=document.createElement('span');
      arrow.className='sort-arrow';th.appendChild(arrow);}
    arrow.textContent=dir==='asc'?'\\u25B2':'\\u25BC';
    rows.sort(function(a,b){
      var av=a.children[idx]?a.children[idx].textContent.trim():'';
      var bv=b.children[idx]?b.children[idx].textContent.trim():'';
      var va=numeric?sortVal(av):av.toLowerCase();
      var vb=numeric?sortVal(bv):bv.toLowerCase();
      if(va<vb)return dir==='asc'?-1:1;
      if(va>vb)return dir==='asc'?1:-1;
      return 0;
    });
    for(var k=0;k<rows.length;k++)tbody.appendChild(rows[k]);
  }
  document.addEventListener('click',function(e){
    if(e.target.tagName==='TH'||e.target.closest('th')){
      sortTable(e.target.tagName==='TH'?e.target:e.target.closest('th'));
    }
  });

  /* task 5.4 — section-level text filter */
  document.addEventListener('input',function(e){
    if(!e.target.classList.contains('section-filter'))return;
    var q=e.target.value.toLowerCase();
    var section=e.target.closest('.section');
    if(!section)return;
    var tables=section.querySelectorAll('table');
    for(var t=0;t<tables.length;t++){
      var tbody=tables[t].querySelector('tbody');
      if(!tbody)continue;
      var rows=tbody.querySelectorAll('tr');
      for(var r=0;r<rows.length;r++){
        var text=rows[r].textContent.toLowerCase();
        rows[r].style.display=(q===''||text.indexOf(q)!==-1)?'':'none';
      }
    }
  });
})();
</script>
"""


def _html_kv(label: str, value: Any) -> str:
    import html

    val_str = "" if value is None else str(value)
    return (
        f'<div class="kv">'
        f"<span>{html.escape(label)}</span>"
        f"<span>{html.escape(val_str)}</span>"
        f"</div>\n"
    )


def _html_section(title: str, content: str) -> str:
    import html

    # task 5.4 — add per-section filter input when the section has tables
    filter_input = ""
    if "<table" in content:
        filter_input = (
            '<input class="section-filter" type="text"'
            ' placeholder="Filter rows..." />\n'
        )
    return (
        f'<div class="section">\n'
        f"<h2>{html.escape(title)}</h2>\n"
        f"{filter_input}"
        f"{content}"
        f"</div>\n"
    )


def _html_table(headers: List[str], rows: List[list]) -> str:
    import html

    head = "".join(
        f'<th>{html.escape(h)}<span class="sort-arrow"></span></th>'
        for h in headers
    )
    body = ""
    for row in rows:
        cells = "".join(
            f"<td>{html.escape(str(c) if c is not None else '')}</td>"
            for c in row
        )
        body += f"<tr>{cells}</tr>\n"
    return (
        f"<table><thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody></table>\n"
    )


def export_html(analyzer: "ROS2LogAnalyzer", output_path: Path) -> None:
    """
    task 18.5 — Generate a self-contained HTML report.

    No JavaScript. Inline CSS. Sections match field summary.
    """
    import html as _html_mod

    from .reports import generate_field_summary

    if analyzer.field_summary is None:
        analyzer.field_summary = generate_field_summary(analyzer)

    s = analyzer.field_summary
    pp = s.pick_performance
    vp = s.vehicle_performance
    mh = s.motor_health_trends
    coord = s.coordination
    nh = s.network_health
    ch = s.communication_health
    pfa = s.pick_failure_analysis
    sh = s.session_health
    cr = s.camera_reliability

    sections = []

    # Pick performance
    content = ""
    content += _html_kv("Total picks", pp.get("total"))
    content += _html_kv("Succeeded", pp.get("succeeded"))
    content += _html_kv("Failed", pp.get("failed"))
    content += _html_kv("Success rate", f"{pp.get('success_rate_pct', 0.0)}%")
    content += _html_kv("Picks / hour", pp.get("picks_per_hour"))
    ct = pp.get("cycle_time_ms", {})
    if ct.get("count"):
        content += _html_kv("Cycle time avg (ms)", ct.get("avg"))
        content += _html_kv("Cycle time p95 (ms)", ct.get("p95"))
    wasted = pp.get("estimated_wasted_detections_pct")
    if wasted is not None:
        content += _html_kv("Est. wasted detections", f"{wasted}%")
    ee = pp.get("ee_duty_cycle_pct")
    if ee is not None:
        content += _html_kv("EE duty cycle", f"{ee}%")
    sections.append(_html_section("Pick Performance", content))

    # Vehicle performance
    content = ""
    content += _html_kv("Drive commands", vp.get("drive_commands"))
    content += _html_kv("Total distance (m)", vp.get("total_distance_m"))
    content += _html_kv("Position reached rate", f"{vp.get('position_reached_rate_pct', 0.0)}%")
    content += _html_kv("cmd_vel count", vp.get("cmd_vel_count"))
    cvl = vp.get("cmd_vel_latency_ms", {})
    if cvl.get("count"):
        content += _html_kv("cmd_vel latency avg (ms)", cvl.get("avg"))
    state_time = vp.get("time_in_state_s", {})
    if state_time:
        rows_s = [[state, f"{secs:.1f}s"] for state, secs in
                  sorted(state_time.items(), key=lambda x: -x[1])]
        content += _html_table(["State", "Duration (s)"], rows_s)
    sections.append(_html_section("Vehicle Performance", content))

    # Motor health
    content = ""
    arm_mh = mh.get("arm", {})
    if arm_mh:
        content += "<h3>Arm Motors (per joint)</h3>\n"
        rows_m = []
        for joint, fields in arm_mh.items():
            temp = fields.get("temp_c", {})
            err = fields.get("err_decoded", "")
            rows_m.append([
                joint,
                f"{temp.get('avg', '')} avg / {temp.get('max', '')} max" if temp.get("count") else "n/a",
                err,
            ])
        content += _html_table(["Joint", "Temp (°C)", "Errors"], rows_m)
    veh_mh = mh.get("vehicle", {})
    hs = veh_mh.get("health_score", {})
    if hs.get("count"):
        content += "<h3>Vehicle Motor Health Score</h3>\n"
        content += _html_kv("avg", hs.get("avg"))
        content += _html_kv("min", hs.get("min"))
    sections.append(_html_section("Motor Health", content))

    # Pick failures
    if pfa:
        content = ""
        content += _html_kv("Text-based failures", pfa.get("text_failure_count"))
        content += _html_kv("Emergency shutdowns", pfa.get("emergency_shutdowns"))
        by_phase = pfa.get("failure_by_phase", {})
        if by_phase:
            rows_p = [[phase, cnt] for phase, cnt in
                      sorted(by_phase.items(), key=lambda x: -x[1])]
            content += _html_table(["Phase", "Count"], rows_p)
        top = pfa.get("top_failure_reasons", [])
        if top:
            rows_r = [[r, c] for r, c in top[:10]]
            content += _html_table(["Reason", "Count"], rows_r)
        oh = pfa.get("recovery_overhead_pct")
        if oh:
            content += _html_kv("Recovery overhead", f"{oh}%")
        sections.append(_html_section("Pick Failure Analysis", content))

    # Coordination
    content = ""
    content += _html_kv("Coordination cycles", coord.get("coordination_cycles"))
    content += _html_kv("Picks during vehicle motion", coord.get("picks_during_vehicle_motion"))
    vs = coord.get("vehicle_stop_ms", {})
    if vs.get("count"):
        content += _html_kv("Vehicle stop ms avg", vs.get("avg"))
    ap = coord.get("arm_phase_ms", {})
    if ap.get("count"):
        content += _html_kv("Arm phase ms avg", ap.get("avg"))
    sections.append(_html_section("Arm-Vehicle Coordination", content))

    # Camera reliability
    content = ""
    content += _html_kv("Reconnections", cr.get("reconnection_count"))
    if cr.get("reconnection_count", 0) > 0:
        content += _html_kv("XLink triggers", cr.get("xlink_triggers"))
        content += _html_kv("Timeout triggers", cr.get("timeout_triggers"))
        mtbr = cr.get("mean_time_between_reconnections_s")
        if mtbr:
            content += _html_kv("MTBR (s)", mtbr)
    sections.append(_html_section("Camera Reliability", content))

    # Network health
    content = ""
    pr = nh.get("ping_router_ms", {})
    if pr.get("count"):
        content += _html_kv("Ping router avg (ms)", pr.get("avg"))
        content += _html_kv("Router packet loss", f"{nh.get('ping_router_loss_pct', 0.0)}%")
    pb = nh.get("ping_broker_ms", {})
    if pb.get("count"):
        content += _html_kv("Ping broker avg (ms)", pb.get("avg"))
        content += _html_kv("Broker packet loss", f"{nh.get('ping_broker_loss_pct', 0.0)}%")
    content += _html_kv("Eth Rx errors", nh.get("eth_rx_errors"))
    content += _html_kv("Eth Tx errors", nh.get("eth_tx_errors"))
    sections.append(_html_section("Network Health", content))

    # Communication health
    content = ""
    content += _html_kv("MQTT uptime", f"{ch.get('mqtt_uptime_pct', 100.0)}%")
    content += _html_kv("Disconnects", ch.get("mqtt_disconnects"))
    content += _html_kv("Unexpected disconnects", ch.get("unexpected_disconnects"))
    content += _html_kv("Publish failures", ch.get("publish_failures"))
    content += _html_kv("Broker restarts", ch.get("broker_restarts"))
    sections.append(_html_section("Communication Health", content))

    # Hourly throughput
    if s.hourly_throughput:
        rows_h = [
            [b["hour"], b["picks_total"], b["picks_succeeded"],
             f"{b['success_rate_pct']:.1f}%",
             f"{b['avg_cycle_time_ms']:.0f}ms" if b.get("avg_cycle_time_ms") else "n/a"]
            for b in s.hourly_throughput
        ]
        content = _html_table(
            ["Hour", "Picks", "Succeeded", "Success Rate", "Avg Cycle Time"],
            rows_h,
        )
        sections.append(_html_section("Hourly Throughput", content))

    # Trend alerts
    if s.trend_alerts:
        content = "<ul>\n"
        for alert in s.trend_alerts:
            content += f'<li class="alert">{_html_mod.escape(alert.get("description", ""))}</li>\n'
        content += "</ul>\n"
        sections.append(_html_section("Trend Alerts", content))

    # Session health
    content = ""
    dur = sh.get("session_duration_s", 0)
    mins = int(dur // 60)
    secs_val = int(dur % 60)
    content += _html_kv("Session duration", f"{mins}m {secs_val}s")
    content += _html_kv("Restarts", sh.get("restarts"))
    content += _html_kv("Log gaps (>30s)", sh.get("log_gaps"))
    content += _html_kv("Clock jumps", sh.get("clock_jumps"))
    content += _html_kv("Manual interventions", sh.get("manual_interventions"))
    sections.append(_html_section("Session Health", content))

    # Assemble full document
    title = f"Log Analysis: {_html_mod.escape(str(analyzer.log_dir))}"
    html_content = (
        "<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
        f"<meta charset='UTF-8'>\n<title>{title}</title>\n"
        f"<style>{_HTML_CSS}</style>\n"
        "</head>\n<body>\n"
        f"<h1>{title}</h1>\n"
        + "".join(sections)
        + _HTML_JS
        + "</body>\n</html>\n"
    )

    output_path.write_text(html_content, encoding="utf-8")


# ---------------------------------------------------------------------------
# task 18.7 — Session comparison
# ---------------------------------------------------------------------------


def compare_sessions(
    analyzer_a: "ROS2LogAnalyzer",
    session_b_dir: str,
    verbose: bool = False,
) -> None:
    """
    task 18.6/18.7 — Compare two sessions side-by-side with deltas.

    Loads session B from session_b_dir, generates field summaries for both,
    then prints a comparison table.
    """
    from .analyzer import ROS2LogAnalyzer
    from .reports import generate_field_summary

    # Analyse session B
    analyzer_b = ROS2LogAnalyzer(session_b_dir, verbose=verbose)
    analyzer_b.analyze()

    if analyzer_a.field_summary is None:
        analyzer_a.field_summary = generate_field_summary(analyzer_a)
    if analyzer_b.field_summary is None:
        analyzer_b.field_summary = generate_field_summary(analyzer_b)

    sa = analyzer_a.field_summary
    sb = analyzer_b.field_summary

    dir_a = str(analyzer_a.log_dir)
    dir_b = session_b_dir

    col_w = 30

    def _hdr2(title: str) -> None:
        print(f"\n{'═' * (col_w * 2 + 24)}")
        print(f"  {title}")
        print(f"{'═' * (col_w * 2 + 24)}")

    def _row2(label: str, val_a: Any, val_b: Any) -> None:
        a_str = "" if val_a is None else str(val_a)
        b_str = "" if val_b is None else str(val_b)
        # Compute delta if both numeric
        delta_str = ""
        try:
            fa = float(a_str.rstrip("%"))
            fb = float(b_str.rstrip("%"))
            diff = fb - fa
            delta_str = f"{diff:+.1f}"
        except (ValueError, AttributeError):
            pass
        print(f"  {label:<30} {a_str:<{col_w}} {b_str:<{col_w}} {delta_str}")

    print(f"\n{'Session A':<{col_w + 32}} {'Session B':<{col_w}}")
    print(f"  {'Metric':<30} {dir_a[-col_w:]:<{col_w}} {dir_b[-col_w:]:<{col_w}} Delta")
    print(f"  {'-'*30} {'-'*col_w} {'-'*col_w} -----")

    _hdr2("PICK PERFORMANCE")
    ppa, ppb = sa.pick_performance, sb.pick_performance
    _row2("Total picks", ppa.get("total"), ppb.get("total"))
    _row2("Success rate (%)", ppa.get("success_rate_pct"), ppb.get("success_rate_pct"))
    _row2("Picks/hour", ppa.get("picks_per_hour"), ppb.get("picks_per_hour"))
    cta = ppa.get("cycle_time_ms", {})
    ctb = ppb.get("cycle_time_ms", {})
    _row2("Cycle time avg (ms)", cta.get("avg"), ctb.get("avg"))

    _hdr2("VEHICLE PERFORMANCE")
    vpa, vpb = sa.vehicle_performance, sb.vehicle_performance
    _row2("Drive distance (m)", vpa.get("total_distance_m"), vpb.get("total_distance_m"))
    _row2("Pos reached rate (%)", vpa.get("position_reached_rate_pct"),
          vpb.get("position_reached_rate_pct"))

    _hdr2("SESSION HEALTH")
    sha, shb = sa.session_health, sb.session_health
    _row2("Duration (s)", sha.get("session_duration_s"), shb.get("session_duration_s"))
    _row2("Restarts", sha.get("restarts"), shb.get("restarts"))
    _row2("Log gaps", sha.get("log_gaps"), shb.get("log_gaps"))

    # ------------------------------------------------------------------
    # task 4.8 — MOTOR HEALTH comparison
    # ------------------------------------------------------------------
    _hdr2("MOTOR HEALTH")
    mha = sa.motor_health_trends
    mhb = sb.motor_health_trends

    # Vehicle health score
    veh_a = (mha.get("vehicle") or {}).get("health_score", {})
    veh_b = (mhb.get("vehicle") or {}).get("health_score", {})
    _row2(
        "Vehicle health score avg",
        veh_a.get("avg") if veh_a.get("count") else "N/A",
        veh_b.get("avg") if veh_b.get("count") else "N/A",
    )
    _row2(
        "Vehicle health score min",
        veh_a.get("min") if veh_a.get("count") else "N/A",
        veh_b.get("min") if veh_b.get("count") else "N/A",
    )

    # Per-motor health from arm summary
    arm_a = mha.get("arm") or {}
    arm_b = mhb.get("arm") or {}
    multi_a = mha.get("multi_arm", False)
    multi_b = mhb.get("multi_arm", False)

    # For multi-arm, arm summary is {arm_id: {joint: stats}};
    # for single-arm it's {joint: stats} directly.
    # Flatten to {motor_label: {health_stats, err_flags_stats}}
    def _flatten_motor_health(
        arm_data: dict, multi: bool,
    ) -> Dict[str, dict]:
        result: Dict[str, dict] = {}
        if multi:
            for arm_id, joints in arm_data.items():
                if not isinstance(joints, dict):
                    continue
                for joint, stats in joints.items():
                    if not isinstance(stats, dict):
                        continue
                    label = f"{arm_id}/{joint}"
                    result[label] = stats
        else:
            for joint, stats in arm_data.items():
                if not isinstance(stats, dict):
                    continue
                result[joint] = stats
        return result

    motors_a = _flatten_motor_health(arm_a, multi_a)
    motors_b = _flatten_motor_health(arm_b, multi_b)
    all_motor_ids = sorted(set(motors_a) | set(motors_b))

    worst_motor: Optional[str] = None
    worst_delta = 0.0

    if all_motor_ids:
        for mid in all_motor_ids:
            ma = motors_a.get(mid, {})
            mb = motors_b.get(mid, {})
            # Health score per joint
            h_a = ma.get("health", {})
            h_b = mb.get("health", {})
            a_avg = h_a.get("avg") if h_a.get("count") else None
            b_avg = h_b.get("avg") if h_b.get("count") else None
            _row2(
                f"  {mid} health avg",
                a_avg if a_avg is not None else "N/A",
                b_avg if b_avg is not None else "N/A",
            )
            # Error count per joint
            e_a = ma.get("err_flags", {})
            e_b = mb.get("err_flags", {})
            err_count_a = sum(
                1 for v in (
                    e_a if isinstance(e_a, list) else []
                ) if v and v != 0
            ) if isinstance(e_a, list) else (
                e_a.get("max", 0) if isinstance(e_a, dict)
                and e_a.get("count") else "N/A"
            )
            err_count_b = sum(
                1 for v in (
                    e_b if isinstance(e_b, list) else []
                ) if v and v != 0
            ) if isinstance(e_b, list) else (
                e_b.get("max", 0) if isinstance(e_b, dict)
                and e_b.get("count") else "N/A"
            )
            _row2(f"  {mid} error count", err_count_a, err_count_b)

            # Track worst motor by health score delta (largest drop)
            if a_avg is not None and b_avg is not None:
                try:
                    delta = float(b_avg) - float(a_avg)
                    if delta < worst_delta:
                        worst_delta = delta
                        worst_motor = mid
                except (ValueError, TypeError):
                    pass

        if worst_motor:
            _row2(
                "Worst motor (largest drop)",
                worst_motor,
                f"{worst_delta:+.2f}",
            )
    else:
        _row2("Motor data", "N/A", "N/A")

    # ------------------------------------------------------------------
    # task 4.9 — DETECTION MODEL comparison
    # ------------------------------------------------------------------
    _hdr2("DETECTION MODEL")
    dqa = sa.detection_quality
    dqb = sb.detection_quality

    has_det_a = bool(dqa and dqa.get("total_requests"))
    has_det_b = bool(dqb and dqb.get("total_requests"))

    # Model path: extracted from detection_summaries if available
    def _extract_model_path(analyzer: "ROS2LogAnalyzer") -> str:
        for ds in analyzer.events.detection_summaries:
            mp = ds.get("model_path") or ds.get("model")
            if mp:
                return str(mp)
        return "N/A"

    model_a = _extract_model_path(analyzer_a)
    model_b = _extract_model_path(analyzer_b)
    _row2("Model path", model_a, model_b)

    det_rate_a = dqa.get("acceptance_rate_pct") if has_det_a else "N/A"
    det_rate_b = dqb.get("acceptance_rate_pct") if has_det_b else "N/A"
    _row2("Detection rate (%)", det_rate_a, det_rate_b)

    # Highlight better detection rate
    if has_det_a and has_det_b:
        try:
            ra = float(dqa.get("acceptance_rate_pct", 0))
            rb = float(dqb.get("acceptance_rate_pct", 0))
            if rb > ra:
                print(f"  {'':30} {'':>{col_w}} ** Session B better **")
            elif ra > rb:
                print(f"  {'':30} ** Session A better **")
        except (ValueError, TypeError):
            pass

    # False positive rate proxy: border_skip_rate_pct as FP indicator
    fp_a = dqa.get("border_skip_rate_pct") if has_det_a else "N/A"
    fp_b = dqb.get("border_skip_rate_pct") if has_det_b else "N/A"
    _row2("Border skip rate (%)", fp_a, fp_b)

    _row2(
        "Total raw detections",
        dqa.get("total_raw") if has_det_a else "N/A",
        dqb.get("total_raw") if has_det_b else "N/A",
    )
    _row2(
        "Total accepted",
        dqa.get("total_accepted") if has_det_a else "N/A",
        dqb.get("total_accepted") if has_det_b else "N/A",
    )

    # ------------------------------------------------------------------
    # task 4.10 — MQTT comparison
    # ------------------------------------------------------------------
    _hdr2("MQTT")
    cha = sa.communication_health
    chb = sb.communication_health

    has_mqtt_a = bool(cha)
    has_mqtt_b = bool(chb)

    _row2(
        "Connects",
        cha.get("mqtt_connects") if has_mqtt_a else "N/A",
        chb.get("mqtt_connects") if has_mqtt_b else "N/A",
    )
    _row2(
        "Disconnects",
        cha.get("mqtt_disconnects") if has_mqtt_a else "N/A",
        chb.get("mqtt_disconnects") if has_mqtt_b else "N/A",
    )
    _row2(
        "Unexpected disconnects",
        cha.get("unexpected_disconnects") if has_mqtt_a else "N/A",
        chb.get("unexpected_disconnects") if has_mqtt_b else "N/A",
    )
    _row2(
        "Publish failures",
        cha.get("publish_failures") if has_mqtt_a else "N/A",
        chb.get("publish_failures") if has_mqtt_b else "N/A",
    )
    _row2(
        "MQTT uptime (%)",
        cha.get("mqtt_uptime_pct") if has_mqtt_a else "N/A",
        chb.get("mqtt_uptime_pct") if has_mqtt_b else "N/A",
    )
    _row2(
        "Broker restarts",
        cha.get("broker_restarts") if has_mqtt_a else "N/A",
        chb.get("broker_restarts") if has_mqtt_b else "N/A",
    )
    _row2(
        "MTBF (s)",
        cha.get("mtbf_s") if has_mqtt_a else "N/A",
        chb.get("mtbf_s") if has_mqtt_b else "N/A",
    )

    # ------------------------------------------------------------------
    # task 4.11 — SCAN EFFECTIVENESS comparison
    # ------------------------------------------------------------------
    _hdr2("SCAN EFFECTIVENESS")
    sea = sa.scan_effectiveness
    seb = sb.scan_effectiveness

    has_scan_a = bool(sea and sea.get("total_scans"))
    has_scan_b = bool(seb and seb.get("total_scans"))

    _row2(
        "Total scans",
        sea.get("total_scans") if has_scan_a else "N/A",
        seb.get("total_scans") if has_scan_b else "N/A",
    )

    # Positions per scan
    pos_a = sea.get("by_position", {}) if has_scan_a else {}
    pos_b = seb.get("by_position", {}) if has_scan_b else {}
    pps_a = len(pos_a) if has_scan_a else "N/A"
    pps_b = len(pos_b) if has_scan_b else "N/A"
    _row2("Positions per scan", pps_a, pps_b)

    # Center vs non-center ratio
    # Convention: position "0" or "0.000m" or index containing "0"
    # is center; everything else is non-center
    def _center_ratio(by_pos: dict) -> Optional[str]:
        if not by_pos:
            return None
        center_found = 0
        noncenter_found = 0
        for pos_key, stats in by_pos.items():
            found = stats.get("found", 0)
            # Treat position "0", "0.0", "0.000m" etc. as center
            try:
                val = float(pos_key.rstrip("m"))
                if abs(val) < 0.001:
                    center_found += found
                else:
                    noncenter_found += found
            except (ValueError, TypeError):
                noncenter_found += found
        total = center_found + noncenter_found
        if total == 0:
            return "0:0"
        return f"{center_found}:{noncenter_found}"

    cr_a = _center_ratio(pos_a) if has_scan_a else "N/A"
    cr_b = _center_ratio(pos_b) if has_scan_b else "N/A"
    _row2("Center:non-center found", cr_a, cr_b)

    _row2(
        "Cotton found total",
        sea.get("total_cotton_found") if has_scan_a else "N/A",
        seb.get("total_cotton_found") if has_scan_b else "N/A",
    )
    _row2(
        "Cotton picked total",
        sea.get("total_cotton_picked") if has_scan_a else "N/A",
        seb.get("total_cotton_picked") if has_scan_b else "N/A",
    )
    _row2(
        "Best position",
        sea.get("best_position") if has_scan_a else "N/A",
        seb.get("best_position") if has_scan_b else "N/A",
    )
    _row2(
        "Worst position",
        sea.get("worst_position") if has_scan_a else "N/A",
        seb.get("worst_position") if has_scan_b else "N/A",
    )

    print()


# ---------------------------------------------------------------------------
# task 18.8 — --analyze rolling stats (for --watch)
# ---------------------------------------------------------------------------


def print_rolling_analysis(analyzer: "ROS2LogAnalyzer") -> None:
    """
    task 18.8 — Print rolling stats for use with --watch --analyze.

    Shows recent picks, current issue count, and session-so-far metrics.
    Designed to be called repeatedly as new log content arrives.
    """
    picks = analyzer.events.picks
    recent = picks[-10:] if len(picks) > 10 else picks

    total = len(picks)
    succeeded = sum(1 for p in picks if p.get("success"))
    rate = round(100.0 * succeeded / total, 1) if total else 0.0

    session_s = (
        (analyzer.end_time - analyzer.start_time)
        if analyzer.start_time and analyzer.end_time
        else 0.0
    )
    pph = round(3600.0 * total / session_s, 1) if session_s > 0 else 0.0

    print(f"\n─── Rolling analysis (session so far) ───")
    print(f"  Picks: {total} total  {succeeded} succeeded  {rate}% rate  {pph}/hr")

    issue_count = len(analyzer.issues)
    high_issues = sum(1 for i in analyzer.issues.values() if i.severity == "high")
    print(f"  Issues: {issue_count} total  {high_issues} high-severity")

    if recent:
        last_pick = recent[-1]
        ts = last_pick.get("_ts")
        pick_id = last_pick.get("pick_id", "?")
        status = "OK" if last_pick.get("success") else "FAILED"
        print(f"  Last pick #{pick_id}: {status}  ({last_pick.get('total_ms', '?')}ms)")
    print()
