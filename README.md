# Punjab Power Supply Tracker & Weather Correlation Engine

An automated asynchronous scraper and data pipeline that tracks real-time power outages across all subdivisions of Punjab, India, and correlates them with localized weather conditions for future predictive analysis.

## 🚀 Features

- **Asynchronous Data Fetching:** Utilizes `httpx` and `asyncio` with semaphores to concurrently fetch power status from hundreds of PSPCL subdivisions without hitting rate limits.
- **Localized Weather Integration:** Integrates real-time weather data (Temperature, Precipitation, Wind Speed, WMO codes) for every district using the Open-Meteo API.
- **Smart Parsing:** Processes raw API responses into a clean, structured JSON format, handling both "OK" statuses and complex outage details (affected areas, JE contacts, and estimated restoration times).
- **Cloud Sync:** Automated bulk-insert pipeline to Supabase for long-term data storage and analysis.
- **Highly Scalable:** Designed to run as a scheduled task (Cron Job) with minimal resource overhead.

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **Concurrency:** `asyncio`, `Semaphore`
- **Networking:** `httpx`
- **Database:** Supabase (PostgreSQL)
- **APIs:** PSPCL Distribution API, Open-Meteo API

## 📋 Prerequisites

- Python installed locally.
- A Supabase project and API keys.
- A valid PSPCL Token ID.

## ⚙️ Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/your-username/punjab-power-tracker.git](https://github.com/your-username/punjab-power-tracker.git)
   cd punjab-power-tracker
