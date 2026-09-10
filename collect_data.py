import csv
import subprocess
import time
import platform
import re
from collections import deque
from librouteros import connect
from librouteros.exceptions import LibRouterosError

import config

def get_icmp_metrics(target_ip):
    """Executes cross-platform ICMP ping (Windows & Linux/macOS) and extracts advanced RTT and loss metrics."""
    system = platform.system().lower()

    # 1. Adjust command parameters based on the OS
    if system == "windows":
        # -n 3 = 3 packets, -w 1000 = timeout 1000ms (1 second) per packet
        cmd = ["ping", "-n", "3", "-w", "1000", target_ip]
    else:
        # -c 3 = 3 packets, -W 1 = timeout 1 second per packet
        cmd = ["ping", "-c", "3", "-W", "1", target_ip]

    try:
        # 2. Use subprocess.run with check=False; capture stdout and stderr
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=8, check=False
        )
        
        output = result.stdout + result.stderr

        # 3. Flexible regex matching: 
        # - Matches "time=" or "waktu="
        # - Handles "=" or "<" (to catch "<1ms" on Windows)
        rtts = [
            float(x)
            for x in re.findall(
                r"(?:time|waktu)[=<](\d+(?:\.\d+)?)", output, re.IGNORECASE
            )
        ]

        # If rtts list is empty, it means 100% RTO or Host Unreachable
        if not rtts:
            return 200.0, 200.0, 0.0, 100.0  # rtt_avg, rtt_max, jitter, loss

        # 4. Calculate metrics if packets returned successfully
        loss = round(((3 - len(rtts)) / 3.0) * 100.0, 2)
        rtt_avg = round(sum(rtts) / len(rtts), 2)
        rtt_max = max(rtts)
        rtt_min = min(rtts)
        jitter = round(rtt_max - rtt_min, 2)

        return rtt_avg, rtt_max, jitter, loss

    except subprocess.TimeoutExpired:
        # Prevent program hanging if ping process takes longer than 8 seconds
        return 200.0, 200.0, 0.0, 100.0
    except Exception:
        # Catch other errors, e.g., 'ping' binary not found
        return 200.0, 200.0, 0.0, 100.0

def collect_telemetry():
    print(f"[+] Connecting to MikroTik router at {config.ROUTER_IP}:{config.ROUTER_PORT}...")

    try:
        api = connect(
            username=config.ROUTER_USER,
            password=config.ROUTER_PASS,
            host=config.ROUTER_IP,
            port=config.ROUTER_PORT,
        )
        print("[+] MikroTik API connection successful!")
    except LibRouterosError as e:
        print(f"[-] Failed to connect to MikroTik API: {e}")
        return

    fieldnames = [
        "timestamp",
        "session_id",
        "interface",
        "rx_bytes_sec",
        "tx_bytes_sec",
        "rx_packets_sec",
        "tx_packets_sec",
        "rx_drops",
        "tx_drops",
        "rx_errors",
        "tx_errors",
        "rtt_avg",
        "rtt_max",
        "jitter",
        "loss",
        "rtt_rolling_avg",
        "rtt_trend",
        "label",  # 0: NORMAL, 1: DEGRADED
    ]

    print(f"[+] Saving dataset to: {config.DATASET_PATH}")
    print("Select the current network condition state to record:")
    print("0 = NORMAL (Healthy and smooth network)")
    print("1 = DEGRADED (Manually injected latency/loss/disruption)")

    try:
        current_label = int(input("Enter label number (default 0): ") or 0)
    except ValueError:
        current_label = 0

    # Unique session_id per run -> used for group-based train/test splitting (prevents data leakage)
    session_id = int(time.time())

    print(f"\n[+] Starting data collection | Session: {session_id} | Label = {current_label} ...\n")

    file_exists = False
    try:
        with open(config.DATASET_PATH, "r"):
            file_exists = True
    except FileNotFoundError:
        pass

    prev_state = {}
    rtt_history = {iface: deque(maxlen=10) for iface in config.WAN_CONFIG.keys()}

    try:
        with open(config.DATASET_PATH, mode="a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()

            while True:
                now = time.time()
                interfaces = list(api.path("interface"))

                for iface_name, target in config.WAN_CONFIG.items():
                    stats = next(
                        (i for i in interfaces if i.get("name") == iface_name),
                        {},
                    )

                    curr_rx_b = int(stats.get("rx-byte", 0))
                    curr_tx_b = int(stats.get("tx-byte", 0))
                    curr_rx_p = int(stats.get("rx-packet", 0))
                    curr_tx_p = int(stats.get("tx-packet", 0))

                    rx_drops = int(stats.get("rx-drop", 0))
                    tx_drops = int(stats.get("tx-drop", 0))
                    rx_errors = int(stats.get("rx-error", 0))
                    tx_errors = int(stats.get("tx-error", 0))

                    rtt_avg, rtt_max, jitter, loss = get_icmp_metrics(target["probe"])

                    rtt_history[iface_name].append(rtt_avg)
                    history_len = len(rtt_history[iface_name])
                    rtt_rolling_avg = round(sum(rtt_history[iface_name]) / history_len, 2)

                    if history_len > 1:
                        rtt_trend = round(rtt_avg - rtt_history[iface_name][0], 2)
                    else:
                        rtt_trend = 0.0

                    if iface_name in prev_state:
                        dt = now - prev_state[iface_name]["time"]
                        if dt <= 0:
                            dt = 1.0

                        rx_bytes_sec = max(0.0, (curr_rx_b - prev_state[iface_name]["rx_b"]) / dt)
                        tx_bytes_sec = max(0.0, (curr_tx_b - prev_state[iface_name]["tx_b"]) / dt)
                        rx_packets_sec = max(0.0, (curr_rx_p - prev_state[iface_name]["rx_p"]) / dt)
                        tx_packets_sec = max(0.0, (curr_tx_p - prev_state[iface_name]["tx_p"]) / dt)

                        row = {
                            "timestamp": int(now),
                            "session_id": session_id,
                            "interface": iface_name,
                            "rx_bytes_sec": round(rx_bytes_sec, 2),
                            "tx_bytes_sec": round(tx_bytes_sec, 2),
                            "rx_packets_sec": round(rx_packets_sec, 2),
                            "tx_packets_sec": round(tx_packets_sec, 2),
                            "rx_drops": rx_drops,
                            "tx_drops": tx_drops,
                            "rx_errors": rx_errors,
                            "tx_errors": tx_errors,
                            "rtt_avg": rtt_avg,
                            "rtt_max": rtt_max,
                            "jitter": jitter,
                            "loss": loss,
                            "rtt_rolling_avg": rtt_rolling_avg,
                            "rtt_trend": rtt_trend,
                            "label": current_label,
                        }

                        writer.writerow(row)
                        f.flush()

                        print(
                            f"[{time.strftime('%H:%M:%S')}] [{target['name']}] "
                            f"RTT: {rtt_avg}ms (Jit: {jitter}) | Trend: {rtt_trend} | Loss: {loss}% | "
                            f"Rx: {round(rx_bytes_sec/1024, 2)} KB/s"
                        )

                    prev_state[iface_name] = {
                        "rx_b": curr_rx_b,
                        "tx_b": curr_tx_b,
                        "rx_p": curr_rx_p,
                        "tx_p": curr_tx_p,
                        "time": now,
                    }

                time.sleep(config.SAMPLE_INTERVAL)

    except KeyboardInterrupt:
        print("\n[-] Dataset collection stopped by user.")
    finally:
        api.close()


if __name__ == "__main__":
    collect_telemetry()
