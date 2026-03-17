# BESS Digital Twin

An open-source BESS (Battery Energy Storage System) digital twin lab deployed on Proxmox using isolated Linux virtual machines for simulation, database, and SCADA.

---

## 🔧 Overview

This project simulates and monitors a Battery Energy Storage System using a modular architecture:

- Python-based BESS simulator
- OPC UA bridge for industrial communication
- PostgreSQL database for telemetry storage
- Ignition SCADA for visualization and alarms
- Proxmox-based virtual lab with network isolation

---

## 🧱 Architecture
---

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

## ⚙️ Features (Current)

- BESS simulation (SOC, power, temperature)
- OPC UA data exchange
- PostgreSQL telemetry logging
- Partial Ignition integration

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
