# Fixer

Fixer is a Windows background performance optimizer that continuously manages process priority and policy based on what you are doing right now, especially gaming and streaming.

## What The Software Does

- Detects user context from running processes and foreground activity.
- Switches runtime behavior between `default`, `gaming`, and `streaming` profiles.
- Raises priority for critical apps (game, streamer) and lowers priority for less important background tasks.
- Detects sustained CPU hogs and applies mode-based remediation.
- Flags suspicious process patterns such as potential miners, keyloggers, and unauthorized recorder processes.
- Supports policy-driven process close/throttle behavior with protected-process safeguards.
- Can run from console, tray, startup registration, or as a Windows service.

## How Fixer Operates In Real Time

1. Scans active processes, CPU usage, and foreground app.
2. Selects the best profile for the current context.
3. Applies profile actions (`boost`, `throttle`, `close`) from config.
4. Monitors for resource abuse and suspicious behavior.
5. Applies safety-mode enforcement and logs every important action.

## Runtime Profiles

- `default`: conservative desktop behavior.
- `gaming`: prioritizes game process responsiveness.
- `streaming`: prioritizes both game and streaming process stability.

## Safety Modes

- `safe`: observe/log only for risky actions; no hard enforcement.
- `balanced`: moderate enforcement such as throttling.
- `aggressive`: strongest enforcement, including termination where policy allows.

## Learning Mode

Learning mode observes repeated runtime patterns and writes local suggestions to help tune configuration.

Suggested targets include:
- `resource_allowlist`
- `suspicious.authorized_recorders`
- `game_processes`
- `streaming_processes`

## What Fixer Is Not

- Not a replacement for antivirus/EDR.
- Not guaranteed to improve every workload equally.
- Not a one-click substitute for proper system tuning, drivers, and thermal management.

## Safety Principles

- Protected system processes are never terminated by policy.
- Start with `safe` mode and `--dry-run` while tuning rules.
- Review logs and learning suggestions before enabling aggressive behavior.
