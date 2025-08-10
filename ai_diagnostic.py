#!/usr/bin/env python3
"""AI Diagnostic Tool - Analyze debug.dat file"""
import re
from collections import defaultdict, Counter
import sys

def analyze_debug_file(filename="debug.dat"):
    """Analyze the debug.dat file for AI patterns"""
    
    # Categories to track
    categories = defaultdict(list)
    timestamps = []
    ai_decisions = []
    worker_states = defaultdict(lambda: {"idle": 0, "gathering": 0, "building": 0})
    resource_counts = defaultdict(Counter)
    build_attempts = []
    gather_failures = []
    barracks_checks = []
    
    # Parse the file
    with open(filename, 'r') as f:
        for line in f:
            # Extract timestamp and category
            match = re.match(r'\[(\d+:\d+:\d+\.\d+)\] \[([^\]]+)\] (.+)', line)
            if not match:
                continue
                
            timestamp = match.group(1)
            category = match.group(2)
            message = match.group(3)
            
            categories[category].append((timestamp, message))
            
            # Track specific patterns
            if "AI_ECONOMY" in category:
                if "Selected action:" in message:
                    ai_decisions.append((timestamp, message))
                elif "Resources:" in message and "{" in message:
                    # Extract resource counts
                    res_match = re.search(r"Resources: ({.*?})", message)
                    if res_match:
                        try:
                            resources = eval(res_match.group(1))
                            for k, v in resources.items():
                                resource_counts[timestamp][k] = v
                        except:
                            pass
                elif "Barracks check" in message:
                    barracks_checks.append((timestamp, message))
                elif "idle workers" in message:
                    match = re.search(r"(\d+) idle workers", message)
                    if match:
                        worker_states[timestamp]["idle"] = int(match.group(1))
                elif "Gather task failed" in message:
                    gather_failures.append((timestamp, message))
                    
            elif "AI_BUILD" in category:
                if "assigning worker" in message:
                    build_attempts.append((timestamp, message))
                    
            elif "BUILD_UPDATE" in category or "CONSTRUCTION" in category:
                # Skip these spammy categories
                continue
    
    # Generate report
    print("=== AI DIAGNOSTIC REPORT ===\n")
    
    # 1. AI Decision Summary
    print("1. AI DECISIONS:")
    action_counts = Counter()
    for ts, msg in ai_decisions[-20:]:  # Last 20 decisions
        action = re.search(r"Selected action: (\w+)", msg)
        if action:
            action_counts[action.group(1)] += 1
            print(f"  {ts}: {action.group(1)}")
    
    print("\nAction Summary:")
    for action, count in action_counts.most_common():
        print(f"  {action}: {count} times")
    
    # 2. Resource Status
    print("\n2. RESOURCE TRACKING:")
    if resource_counts:
        last_timestamp = max(resource_counts.keys())
        print(f"Last known resources at {last_timestamp}:")
        for res, amount in resource_counts[last_timestamp].items():
            print(f"  {res}: {amount}")
    
    # 3. Barracks Attempts
    print("\n3. BARRACKS BUILD ATTEMPTS:")
    for ts, msg in barracks_checks[-5:]:  # Last 5 checks
        print(f"  {ts}: {msg}")
        # Look for following lines
        idx = categories["AI_ECONOMY"].index((ts, msg))
        for i in range(1, min(5, len(categories["AI_ECONOMY"]) - idx)):
            next_ts, next_msg = categories["AI_ECONOMY"][idx + i]
            if "Barracks" in next_msg or "Can afford" in next_msg:
                print(f"    -> {next_msg}")
    
    # 4. Worker Issues
    print("\n4. WORKER ISSUES:")
    print(f"Gather failures: {len(gather_failures)}")
    for ts, msg in gather_failures[-5:]:
        print(f"  {ts}: {msg}")
    
    # 5. Building Activity
    print("\n5. BUILDING ACTIVITY:")
    print(f"Build attempts: {len(build_attempts)}")
    for ts, msg in build_attempts[-5:]:
        print(f"  {ts}: {msg}")
    
    # 6. Category Summary
    print("\n6. LOG CATEGORY SUMMARY:")
    for cat, entries in sorted(categories.items(), key=lambda x: len(x[1]), reverse=True):
        print(f"  {cat}: {len(entries)} entries")
    
    # 7. Look for specific issues
    print("\n7. POTENTIAL ISSUES:")
    
    # Check if AI is stuck on one action
    if action_counts and action_counts.most_common(1)[0][1] > 10:
        print(f"  WARNING: AI seems stuck on '{action_counts.most_common(1)[0][0]}' action")
    
    # Check if workers are idling
    idle_count = 0
    for entries in worker_states.values():
        if entries["idle"] > 2:
            idle_count += 1
    if idle_count > 5:
        print(f"  WARNING: High idle worker count detected ({idle_count} times)")
    
    # Check if barracks is never affordable
    barracks_affordable = False
    for ts, msg in barracks_checks:
        if "Can afford: True" in msg:
            barracks_affordable = True
            break
    if not barracks_affordable and len(barracks_checks) > 3:
        print("  WARNING: Barracks never affordable despite multiple checks")

if __name__ == "__main__":
    analyze_debug_file()