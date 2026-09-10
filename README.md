```markdown
# 🚀 Adaptive Multi-WAN Failover on MikroTik via Network Telemetry & AI

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![RouterOS Version](https://img.shields.io/badge/RouterOS-v7-orange.svg)](https://mikrotik.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An intelligent **Adaptive Multi-WAN Failover** system for MikroTik routers. It combines multivariate network telemetry with machine learning to automatically detect and respond to **Silent Degradation** on internet links.

---

## 📌 Problem Statement: Silent Degradation

Traditional failover mechanisms (such as basic Netwatch or Ping Check Gateway) only trigger when a link completely fails (**Hard Failure**).

However, modern networks frequently suffer from **Silent Degradation**:
* Physical link remains **UP**.
* Local gateway is still reachable via ping.
* **Yet**, latency spikes, jitter fluctuates unpredictably, packet loss occurs, and usable throughput drops drastically.

This project addresses silent degradation by continuously assessing the relative quality of multiple WAN connections in real time using an **AI/Machine Learning** model.

---

## 🏗️ System Architecture & Principles

```text
                     INTERNET
                    /        \
                   /          \
           ISP A (60 Mbps)    ISP B (20 Mbps)
                  │              │
                  └───────┬──────┘
                          │
                   ┌──────▼──────┐
                   │  MikroTik   │ (Main Routing Engine)
                   │  RouterOS   │
                   └──────┬──────┘
                          │
                         LAN
                          │
                  ┌───────▼───────┐
                  │   AI Server   │ (External Decision Layer)
                  │    Python     │
                  └───────────────┘

```

1. **Router Decides Packets, AI Decides Policy:** The AI Server only modifies routing preferences (Administrative Distance) via RouterOS API. RouterOS handles actual packet forwarding and routing.
2. **Out-of-Band Architecture:** The AI Server resides on the LAN and is **not in the packet forwarding path**. If the AI Server crashes or disconnects, network traffic continues uninterrupted via MikroTik's native recursive routing.
3. **Hysteresis & Cooldown:** Failover and failback actions require consecutive confirmed observations to prevent route flapping.
4. **Safe Routing States:** The AI is strictly restricted to valid administrative distance values (e.g., `1`, `2`, `3`).

---

## ✨ Key Features

* **Multivariate Telemetry Collector:** Gathers RTT Average, RTT Max, Jitter, Packet Loss, Rolling Trends, and interface traffic statistics via RouterOS API.
* **Random Forest ML Classifier:** Classifies real-time network states (`0 = NORMAL`, `1 = DEGRADED`).
* **Hysteresis Guard:**
* **Failover:** Triggered after 2 consecutive `DEGRADED` samples.
* **Failback:** Triggered after 3 consecutive `HEALTHY` samples.


* **Real-time Telegram Alerts:** Instant notifications sent to network engineers whenever routing preferences change.
* **Anti-Data Leakage Pipeline:** Session-based telemetry tagging (`session_id`) ensuring proper Group-based Train/Test splitting during model training.

---

## 🛠️ Prerequisites

* **MikroTik RouterOS v7** (API port `8728` enabled)
* **Python 3.8+**
* **Linux Impairment Box** (*Optional*, for simulating network degradation using `tc netem`)

---

## 🚀 Quick Start (Using Pre-trained Model)

If you want to deploy the system immediately using the pre-trained Machine Learning model in the `models/` folder:

### 1. Clone Repository & Install Dependencies

```bash
git clone [https://github.com/your-username/mikrotik-ai-failover.git](https://github.com/your-username/mikrotik-ai-failover.git)
cd mikrotik-ai-failover
pip install -r requirements.txt

```

### 2. Configure Credentials

Create a `config.py` file from the provided template:

```bash
cp config.py.example config.py

```

Edit `config.py` with your MikroTik IP, API credentials, WAN interface names, and Telegram Bot details:

```python
ROUTER_IP = "172.16.1.1"
ROUTER_USER = "AI"
ROUTER_PASS = "your_password"

TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID = "your_chat_id"

```

### 3. Run Main Engine

Start the AI Controller:

```bash
python main_engine.py

```

The system will start monitoring live telemetry, classifying quality, and applying failover rules automatically.

---

## 🔬 Advanced Workflow (Collecting Data & Training Custom Model)

If you want to collect custom network telemetry and train a model tailored to your specific ISP parameters:

### 1. Simulate Network Impairment (Linux Box)

Use a Linux machine acting as a gateway or emulator (`tc netem`) to inject artificial degradation into your test path:

```bash
# Inject 120ms latency and 4% packet loss on ISP A interface
sudo tc qdisc add dev eth1 root netem delay 120ms 30ms loss 4%

```

### 2. Collect Custom Dataset

Run the telemetry collection script:

```bash
python collect_data.py

```

* Enter `0` when recording **NORMAL** healthy network state.
* Inject impairment via `tc netem`, re-run the script, and enter `1` for **DEGRADED** network state.

The telemetry will be saved to `dataset/real_telemetry.csv` with unique experiment `session_id` tags.

### 3. Train Custom AI Model

Train the Machine Learning classifier on your collected dataset:

```bash
python train_model.py

```

This updates `models/ai_model.joblib` and `models/feature_names.joblib`.

### 4. Run Main Engine

Execute the controller with your newly trained model:

```bash
python main_engine.py

```

---

## 🖥️ Running as a Systemd Service (Background Service)

To ensure the AI engine starts automatically on Linux boot, configure it as a `systemd` daemon:

1. Create a service unit file:
```bash
sudo nano /etc/systemd/system/mikrotik-ai.service

```


2. Add the following configuration:
```ini
[Unit]
Description=MikroTik AI Multi-WAN Controller Service
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/mikrotik-ai-failover
ExecStart=/usr/bin/python3 /path/to/mikrotik-ai-failover/main_engine.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target

```


3. Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mikrotik-ai.service

```



---

## 📄 Repository Structure

```text
.
├── dataset/             # Telemetry CSV storage (real_telemetry.csv)
├── models/              # Pre-trained ML model and feature list (.joblib)
├── config.py.example    # Configuration template
├── collect_data.py      # Telemetry Data Collector script
├── train_model.py       # Random Forest ML Trainer
├── router_controller.py # RouterOS API Route Controller
├── notifier.py          # Telegram Bot Alert Helper
├── main_engine.py       # Main AI Decision & Hysteresis Controller
├── requirements.txt     # Python Dependencies
└── README.md            # Project Documentation

```

---

## 📝 License

Distributed under the [MIT License](https://www.google.com/search?q=LICENSE). Free for educational, research, and production use.

```

```
