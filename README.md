
# EV-OptiGrid ⚡
### An AI-Powered Personalized EV Charging, Route & Energy Optimization System

EV-OptiGrid is an intelligent electric vehicle (EV) charging optimization platform that helps users make smarter charging decisions based on battery level, journey requirements, electricity prices, grid demand, renewable energy availability, and personal preferences.

The project combines **Machine Learning, stochastic optimization, and full-stack development** to provide personalized charging recommendations, route planning, charging station rankings, and energy usage insights.

## 🚀 Key Features

- **Smart Charging Optimization:** Recommends when, where, and how much to charge using battery conditions, predicted energy prices, grid demand, and user preferences.
- **Machine Learning Predictions:** Uses ML models to estimate electricity prices, grid load, solar generation, station queues, and charging demand.
- **Journey Planner:** Supports journey-aware charging decisions based on travel and charging requirements.
- **Charging Station Ranking:** Ranks charging opportunities using the Charging Opportunity Score (COS), considering cost, distance, charging speed, queue time, battery impact, grid conditions, and renewable energy.
- **Personalized User Profiles:** Supports different charging preferences and optimization strategies.
- **EV Digital Twin & Simulator:** Simulates EV charging scenarios and compares different charging policies.
- **Battery Health Insights:** Considers battery degradation and charging-related battery wear.
- **Explainable Recommendations:** Provides insights into why a charging action is recommended.
- **Fleet Optimization:** Compares charging strategies across simulated EV fleets.
- **EV Charging Copilot:** Provides an interface for exploring charging decisions and energy insights.

## 🛠️ Technology Stack

| Component | Technologies |
|---|---|
| Frontend | Next.js 14, React, TypeScript |
| Backend | Python, FastAPI |
| Machine Learning | XGBoost, Random Forest, Gradient Boosting |
| Optimization | Stochastic Dynamic Programming, Value Iteration, Monte Carlo Simulation |
| Database | SQLAlchemy, SQLite, Alembic |
| Authentication | JWT Authentication |
| Background Jobs | APScheduler |
| Testing | Pytest, Vitest, End-to-End Tests |

## 🏗️ System Architecture

```text
          User / EV Fleet
                 |
                 v
       Next.js Frontend
                 |
                 v
          FastAPI Backend
                 |
       +---------+---------+
       |         |         |
       v         v         v
   ML Models  Charging   Database
              Optimizer
                 |
                 v
      Personalized Recommendations
                 |
       +---------+----------+
       |         |          |
       v         v          v
   Smart      Journey     Battery &
   Charging   Planning    Energy Insights
```

## ⚙️ How It Works

1. **Input Collection:** Uses battery level, journey details, charging preferences, and available energy information.
2. **Prediction:** Machine learning models estimate relevant charging conditions, including prices, grid load, solar availability, and station queues.
3. **Optimization:** A stochastic optimization approach evaluates charging decisions under uncertain conditions.
4. **Station Evaluation:** Charging opportunities are ranked using multiple cost, convenience, energy, and battery-related factors.
5. **Recommendation:** The system presents personalized charging suggestions and supporting explanations.
6. **Simulation:** Different charging policies can be evaluated across simulated scenarios to compare their performance.

## 📂 Project Structure

```text
EV-OptiGrid/
├── backend/          # FastAPI backend and APIs
├── frontend/         # Next.js web application
├── README.md
└── ...
```

## 💻 Getting Started

### Prerequisites

Make sure the following are installed:

- Python 3.10–3.12
- Node.js 18 or later
- npm
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/aditibh19/optigrid.git
cd optigrid
```

### 2. Set Up the Project

On Windows, run the setup script from the project root:

```bat
setup.bat
```

This prepares the local development environment and installs the required dependencies.

### 3. Start the Application

```bat
start.bat
```

When the services start successfully, open:

- **Frontend:** http://localhost:3000
- **Backend API Documentation:** http://localhost:8000/docs

Follow the setup scripts and terminal output if any additional configuration is required.

## 📊 Data & Evaluation

EV-OptiGrid supports simulated charging scenarios, prediction workflows, and comparisons between charging strategies.

Some datasets and station or route information use synthetic or demonstration data. Real-world provider integration depends on the required API configuration. Results should therefore be interpreted according to the data source used in each scenario.

## 🔐 Security & Reliability

- JWT-based authentication
- Access controls for user-owned data
- Database migrations with Alembic
- Automated backend and frontend testing
- Background task scheduling

## 🔮 Future Improvements

- Integrate verified real-time EV charging station and electricity pricing APIs.
- Incorporate live traffic and journey-time predictions.
- Connect MQTT-based charging device telemetry.
- Improve renewable energy forecasting using real-world datasets.
- Deploy the frontend and backend with production-ready configuration.
- Evaluate optimization performance using real EV charging data.

## 👩‍💻 Author

**Aditi Bhalla**

B.Tech in Information Technology | Jaypee Institute of Information Technology (JIIT), Noida

GitHub: [@aditibh19](https://github.com/aditibh19)

---

*EV-OptiGrid — Making EV charging smarter, more personalized, and energy-aware.*
