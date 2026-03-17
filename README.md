# BESS Digital Twin

An open-source BESS (Battery Energy Storage System) digital twin lab deployed on Proxmox using isolated Linux virtual machines for simulation, database, and SCADA.
---

## 🔧 Overview
This project models a real-world BESS architecture using a distributed, multi-VM design to simulate industrial control systems.
It simulates and monitors a Battery Energy Storage System using a modular architecture:

- Python-based BESS simulator
- OPC UA bridge for industrial communication
- PostgreSQL database for telemetry storage
- Ignition SCADA for visualization and alarms
- Proxmox-based virtual lab with network isolation

---

## 🧱 Architecture
---
Simulation VM (Python BESS Simulator)
        ↓
OPC UA Bridge
        ↓
Database VM (PostgreSQL / TimescaleDB)
        ↓
Ignition SCADA VM

## 🖥️ Infrastructure

The system is deployed on Proxmox using separate virtual machines:

- **Simulation VM**
  - Runs BESS simulator and OPC UA bridge

- **Database VM**
  - Runs PostgreSQL for telemetry and event storage

- **Ignition VM**
  - Runs Ignition SCADA for dashboards and alarms

---

## 🌐 Network Design

- Dedicated lab network separate from main network
- Mimics industrial OT network segmentation
- Controlled communication between system components

---

## ⚙️ ⚙️ Features

- Scalable BESS simulation (10 inverters, 20 battery units)
- Real-time telemetry generation:
  - State of Charge (SOC)
  - Voltage
  - Current
  - Power (active/reactive if applicable)
- Equipment status and state modelling:
  - Running / Standby / Fault states
- Fault simulation:
  - Over-temperature
  - Overcurrent
  - Communication loss
  - Battery/PCS fault conditions
- OPC UA data exchange for industrial communication
- PostgreSQL telemetry logging (historian)
- Ignition SCADA integration (partial, in progress)
- Multi-VM deployment on Proxmox
- Isolated lab network mimicking OT system segmentation

---

## 🚧 Work in Progress

- Alarm management system
- OPC UA namespace cleanup
- Ignition dashboards
- EMS (Energy Management System) logic

---

## 🛠️ Tech Stack

- Python
- OPC UA (python-opcua)
- PostgreSQL / TimescaleDB (planned)
- Ignition SCADA
- Proxmox VE

---

## 📁 Project Structure (Planned)

simulator/      # BESS simulation logic
opcua/          # OPC UA bridge and models
db/             # Database schema and queries
ignition/       # SCADA notes and screenshots
infra/          # Proxmox + network design
docs/           # Architecture and roadmap

---
## 🎯 Goal

To build a realistic, modular, and scalable BESS digital twin platform for:

- testing control strategies
- simulating grid interactions
- learning industrial automation systems
- developing EMS algorithms
- learning digital twin architectures
- a reusable automation lab

---

## 📌 Status

🚧 Active development

---

## 📈 Future Plans

- EMS dispatch and optimisation
- anomaly detection and AI based analytics.
- multi-inverter system scaling
- containerised deployment
