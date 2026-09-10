# mikrotik_projek/main_engine.py

import time
import joblib
import pandas as pd
from collections import deque
from librouteros import connect

import config
from collect_data import get_icmp_metrics
from router_controller import set_gateway_distance
from notification import send_telegram_alert

def get_isp_state(model, expected_features, iface_name, target, api, prev_state, rtt_history, now):
    """
    Retrieves live telemetry for 1 interface, constructs features EXACTLY as during
    training, and requests the model to predict the status (0 = NORMAL, 1 = DEGRADED).
    """
    interfaces = list(api.path("interface"))
    stats = next((i for i in interfaces if i.get("name") == iface_name), {})

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
    rtt_trend = round(rtt_avg - rtt_history[iface_name][0], 2) if history_len > 1 else 0.0

    prev = prev_state[iface_name]
    dt = now - prev.get("time", now - 1)
    if dt <= 0:
        dt = 1.0

    rx_bytes_sec = max(0.0, (curr_rx_b - prev.get("rx_b", curr_rx_b)) / dt)
    tx_bytes_sec = max(0.0, (curr_tx_b - prev.get("tx_b", curr_tx_b)) / dt)
    rx_packets_sec = max(0.0, (curr_rx_p - prev.get("rx_p", curr_rx_p)) / dt)
    tx_packets_sec = max(0.0, (curr_tx_p - prev.get("tx_p", curr_tx_p)) / dt)

    prev_state[iface_name] = {
        "rx_b": curr_rx_b, "tx_b": curr_tx_b,
        "rx_p": curr_rx_p, "tx_p": curr_tx_p,
        "time": now,
    }

    # Must be EXACTLY the same as feature columns during training (see feature_names.joblib)
    live_data = {
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
    }

    df_live = pd.DataFrame([live_data])[expected_features]
    state = int(model.predict(df_live)[0])

    status_icon = "🟢" if state == 0 else "🔴"
    print(f"[{status_icon}] {target['name']} ({iface_name}) | RTT: {rtt_avg}ms | Jitter: {jitter} | "
          f"Trend: {rtt_trend} | Loss: {loss}%")

    return state


def run_engine():
    print("[+] Loading AI Model from models/ folder...")
    model = joblib.load(config.MODEL_PATH)
    expected_features = joblib.load(config.FEATURES_PATH)

    api = connect(
        username=config.ROUTER_USER,
        password=config.ROUTER_PASS,
        host=config.ROUTER_IP,
        port=config.ROUTER_PORT,
    )
    print("[+] Connected to MikroTik API!\n")

    wan_names = list(config.WAN_CONFIG.keys())  # ["ether1", "ether2"]
    iface_a, iface_b = wan_names[0], wan_names[1]

    prev_state = {iface: {} for iface in wan_names}
    rtt_history = {iface: deque(maxlen=10) for iface in wan_names}

    # --- Hysteresis state (prevents decision making based on a single sample) ---
    degraded_streak = {iface_a: 0, iface_b: 0}
    healthy_streak = {iface_a: 0, iface_b: 0}
    confirmed_state = {iface_a: 0, iface_b: 0}  # status validated by hysteresis

    cooldown_timer = 0

    while True:
        now = time.time()
        print(f"\n--- Monitoring Paths ({time.strftime('%H:%M:%S')}) ---")

        if cooldown_timer > 0:
            cooldown_timer -= 1
            print(f"[⌛] Cooldown active ({cooldown_timer} cycles remaining)")

        raw_state_a = get_isp_state(model, expected_features, iface_a, config.WAN_CONFIG[iface_a],
                                     api, prev_state, rtt_history, now)
        raw_state_b = get_isp_state(model, expected_features, iface_b, config.WAN_CONFIG[iface_b],
                                     api, prev_state, rtt_history, now)

        # --- Update hysteresis counter per ISP ---
        for iface, raw in ((iface_a, raw_state_a), (iface_b, raw_state_b)):
            if raw == 1:
                degraded_streak[iface] += 1
                healthy_streak[iface] = 0
            else:
                healthy_streak[iface] += 1
                degraded_streak[iface] = 0

            if confirmed_state[iface] == 0 and degraded_streak[iface] >= config.CONSECUTIVE_DEGRADED_NEEDED:
                confirmed_state[iface] = 1
            elif confirmed_state[iface] == 1 and healthy_streak[iface] >= config.CONSECUTIVE_HEALTHY_NEEDED:
                confirmed_state[iface] = 0

        state_a = confirmed_state[iface_a]
        state_b = confirmed_state[iface_b]

        if cooldown_timer == 0:
            changed = False
            comment_a = config.WAN_CONFIG[iface_a]["route_comment"]
            comment_b = config.WAN_CONFIG[iface_b]["route_comment"]
            msg = None

            if state_a == 0 and state_b == 0:
                c1 = set_gateway_distance(api, comment_a, 1)
                c2 = set_gateway_distance(api, comment_b, 2)
                if c1 or c2:
                    changed = True
                    msg = (
                        "*[AI-FAILOVER ALERT]*\n\n"
                        "*ISP A:* HEALTHY (Distance 1)\n"
                        "*ISP B:* HEALTHY (Distance 2)\n\n"
                        "💡 *Action:* Traffic switched to ISP A."
                    )

            elif state_a == 1 and state_b == 0:
                print("[ALERT] ISP A degraded (confirmed)! Switching to ISP B...")
                c1 = set_gateway_distance(api, comment_a, 3)
                c2 = set_gateway_distance(api, comment_b, 1)
                if c1 or c2:
                    changed = True
                    msg = (
                        "*[AI-FAILOVER ALERT]*\n\n"
                        "*ISP A:* DEGRADED (Distance 3)\n"
                        "*ISP B:* HEALTHY (Distance 1)\n\n"
                        "💡 *Action:* Traffic switched to ISP B."
                    )

            elif state_a == 0 and state_b == 1:
                print("[ALERT] ISP B degraded (confirmed)! Maintaining ISP A...")
                c1 = set_gateway_distance(api, comment_a, 1)
                c2 = set_gateway_distance(api, comment_b, 3)
                if c1 or c2:
                    changed = True
                    msg = (
                        "*[AI-FAILOVER ALERT]*\n\n"
                        "*ISP A:* HEALTHY (Distance 1)\n"
                        "*ISP B:* DEGRADED (Distance 3)\n\n"
                        "💡 *Action:* Traffic switched to ISP A."
                    )

            else:
                print("[CRITICAL] Both ISPs degraded! Least-bad path -> ISP A.")
                c1 = set_gateway_distance(api, comment_a, 1)
                c2 = set_gateway_distance(api, comment_b, 2)
                if c1 or c2:
                    changed = True
                    msg = (
                        "*[AI-FAILOVER ALERT]*\n\n"
                        "*ISP A:* DEGRADED (Distance 1)\n"
                        "*ISP B:* DEGRADED (Distance 2)\n\n"
                        "💡 *Action:* Traffic switched to ISP A."
                    )

            # Notifications are ONLY sent if route distance actually changes
            if changed and msg:
                send_telegram_alert(msg)
                cooldown_timer = config.COOLDOWN_LIMIT
                print("[!] Routing change executed & Telegram notification sent.")

        time.sleep(config.SAMPLE_INTERVAL)


if __name__ == "__main__":
    run_engine()
