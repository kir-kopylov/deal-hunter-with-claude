#!/usr/bin/env python3
"""Generate launchd plist files from $DEAL_HUNTER_HOME/data/schedule.yaml.

Run after editing schedule.yaml:
    python3 $DEAL_HUNTER_HOME/scripts/generate_launchd.py
    launchctl unload ~/Library/LaunchAgents/com.kkopylov.deals.*.plist 2>/dev/null
    launchctl load   ~/Library/LaunchAgents/com.kkopylov.deals.*.plist
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

HOME = Path.home()
DEAL_HUNTER_HOME = Path(os.environ.get("DEAL_HUNTER_HOME", str(HOME / ".claude")))
SCHEDULE_YAML = DEAL_HUNTER_HOME / "data" / "schedule.yaml"
LAUNCH_AGENTS = HOME / "Library" / "LaunchAgents"
LOG_DIR = DEAL_HUNTER_HOME / "logs"
SCRIPT = DEAL_HUNTER_HOME / "scripts" / "run-deals.sh"

LABEL_PREFIX = "com.kkopylov.deals"

DAY_NAME_TO_NUM = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}


def calendar_intervals_for_group(schedules: list[dict]) -> list[dict]:
    """Convert schedule.yaml entries to launchd StartCalendarInterval dicts."""
    out = []
    for entry in schedules:
        days = entry["day"]
        hour = int(entry["hour"])
        minute = int(entry["minute"])
        if days == "*":
            out.append({"Hour": hour, "Minute": minute})
        else:
            day_list = days if isinstance(days, list) else [days]
            for d in day_list:
                if d not in DAY_NAME_TO_NUM:
                    raise ValueError(f"Unknown day: {d!r}. Use sun/mon/.../sat.")
                out.append(
                    {
                        "Weekday": DAY_NAME_TO_NUM[d],
                        "Hour": hour,
                        "Minute": minute,
                    }
                )
    return out


def render_plist(label: str, group: str, intervals: list[dict]) -> str:
    """Render a launchd plist XML for one group."""
    interval_xml = ""
    for iv in intervals:
        items = "\n        ".join(f"<key>{k}</key><integer>{v}</integer>" for k, v in iv.items())
        interval_xml += f"      <dict>\n        {items}\n      </dict>\n"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{escape(label)}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>{escape(str(SCRIPT))}</string>
    <string>{escape(group)}</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
{interval_xml}  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>{escape(str(LOG_DIR / f"launchd-{group}.out"))}</string>
  <key>StandardErrorPath</key>
  <string>{escape(str(LOG_DIR / f"launchd-{group}.err"))}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>SOURCE_GROUP</key>
    <string>{escape(group)}</string>
    <key>HOME</key>
    <string>{escape(str(HOME))}</string>
    <key>DEAL_HUNTER_HOME</key>
    <string>{escape(str(DEAL_HUNTER_HOME))}</string>
  </dict>
</dict>
</plist>
"""


def main() -> int:
    if not SCHEDULE_YAML.exists():
        print(f"ERROR: {SCHEDULE_YAML} not found", file=sys.stderr)
        return 1
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    with SCHEDULE_YAML.open() as f:
        cfg = yaml.safe_load(f)

    written = []
    for group_name, group_cfg in cfg["groups"].items():
        intervals = calendar_intervals_for_group(group_cfg["schedule"])
        label = f"{LABEL_PREFIX}.{group_name}"
        plist_path = LAUNCH_AGENTS / f"{label}.plist"
        plist_path.write_text(render_plist(label, group_name, intervals))
        written.append(str(plist_path))
        print(f"  wrote {plist_path}  ({len(intervals)} interval(s))")

    print(f"\nDone. {len(written)} plist file(s) generated.")
    print("\nNext steps:")
    print("  launchctl unload ~/Library/LaunchAgents/com.kkopylov.deals.*.plist 2>/dev/null")
    print("  launchctl load   ~/Library/LaunchAgents/com.kkopylov.deals.*.plist")
    print("  launchctl list | grep com.kkopylov.deals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
