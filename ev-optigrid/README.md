
# EV-OptiGrid ⚡
### An AI-Powered Personalized EV Charging, Route & Energy Optimization System

**JIIT Major Project** · Aditi Bhalla · Kashvi Rathore · Arav Gulati  
**Supervisor:** Dr. Prashant Kaushik

EV-OptiGrid is an intelligent, journey-aware EV charging optimization platform that combines machine learning, stochastic dynamic programming, and simulation to recommend when, where, how much, and how fast an electric vehicle should charge.

Instead of simply listing charging stations, EV-OptiGrid considers battery state, journey requirements, electricity prices, grid load, solar availability, charging queues, and user preferences to generate personalized charging recommendations.

## 🚀 Key Features

- **Intelligent Charging Optimization:** Uses stochastic dynamic programming and value iteration to evaluate charging decisions under uncertain conditions.
- **Machine Learning Forecasting:** Uses XGBoost, Random Forest, and Gradient Boosting models trained on project datasets to forecast electricity prices, grid load, solar generation, station queues, and charging demand.
- **Personalized Charging Profiles:** Supports five strategies — Save Money, Fastest, Battery Health, Green, and Balanced.
- **Journey Planning:** Evaluates energy requirements, arrival feasibility, and charging opportunities along a route.
- **Charging Station Ranking:** Calculates a Charging Opportunity Score (COS) based on cost, distance, charging speed, queue, battery impact, grid conditions, and renewable availability.
- **Dynamic Re-optimization:** Recalculates charging recommendations when prices or grid conditions change.
- **Battery Health Analysis:** Considers charging speed, time spent at high charge levels, depth of discharge, and temperature.
- **Fleet Optimization:** Prioritizes vehicles according to urgency while respecting charger and grid constraints.
- **Simulation & Evaluation:** Compares charging strategies using Monte Carlo simulation, fleet experiments, confidence intervals, and a digital twin.
- **Explainable Decisions:** Provides state-space visualizations, policy heatmaps, Bellman equation calculations, and sensitivity analysis.

## 🧠 Technology Stack

| Component | Technologies |
|---|---|
| Frontend | Next.js 14, React, TypeScript |
| Backend | Python, FastAPI |
| Machine Learning | XGBoost, Random Forest, Gradient Boosting, scikit-learn |
| Optimization | Stochastic Dynamic Programming, Value Iteration, Markov Decision Process (MDP) |
| Simulation | Monte Carlo Simulation, Fleet Simulation, Digital Twin |
| Database | SQLite, SQLAlchemy, Alembic |
| Authentication | JWT access and refresh tokens |
| Testing | pytest, Vitest, end-to-end tests |

## 🏗️ System Architecture

```text
User Interface
  Next.js + TypeScript
          |
          v
     FastAPI Backend
          |
          +-------------------+
          |                   |
          v                   v
  ML Forecasting       Journey & Battery Models
          |                   |
          +---------+---------+
                    |
                    v
        Stochastic MDP Optimizer
          Value Iteration
                    |
                    v
       Charging Recommendations
                    |
                    v
     Simulation & Policy Evaluation
```

## ⚙️ How It Works

1. **Collect inputs:** Read the vehicle's battery state, journey requirements, charging preferences, and available system data.
2. **Forecast conditions:** Generate model-based predictions for relevant electricity, grid, solar, queue, and demand conditions.
3. **Evaluate decisions:** Model battery levels, time slots, uncertain conditions, charging actions, and battery-wear costs.
4. **Optimize the policy:** Apply value iteration to evaluate charging actions and select a policy that balances cost, journey needs, and battery health.
5. **Rank stations:** Score charging opportunities against user preferences and journey constraints.
6. **Evaluate performance:** Compare optimized charging with baseline policies through simulation and report the resulting trade-offs.

## 💻 Run Locally

### Prerequisites

- Python 3.10, 3.11, or 3.12
- Node.js 18 or newer
- Git (optional, for cloning the repository)

### Installation

Clone the repository:

```bash
git clone https://github.com/aditibh19/optigrid.git
cd optigrid/ev-optigrid
```

If your repository already opens directly at the project root, use `cd optigrid` instead.

**Windows**

```bat
setup.bat
start.bat
```

**macOS / Linux**

```bash
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

Open the application:

- **Web application:** http://localhost:3000
- **API documentation:** http://localhost:8000/docs

For detailed instructions, troubleshooting, and a guided project demonstration, see [`RUN_ON_YOUR_LAPTOP.md`](RUN_ON_YOUR_LAPTOP.md).

## 🧪 Testing

The project documentation reports the following test coverage:

- **289 backend tests** using pytest
- **23 frontend tests** using Vitest
- **36 end-to-end checks** against the running application

Run the backend tests on Windows:

```powershell
backend\.venv\Scripts\python -m pytest
```

Run frontend tests:

```bash
cd frontend
npm test
```

Run end-to-end checks after starting the application:

```bash
cd frontend
npm run e2e
```

See [`docs/TESTING.md`](docs/TESTING.md) for the documented verification results and limitations.

## 📊 Data & Limitations

- Machine-learning training datasets are synthetic or project-generated.
- Charging stations, routes, and forecasts use demo or synthetic data unless supported external providers are configured.
- Forecasts represent model predictions and should not be interpreted as guaranteed live market or grid measurements.
- SQLite is the default database for local development.
- PostgreSQL and external provider integrations require additional configuration and have not been verified according to the project documentation.
- The Windows setup scripts and actual browser appearance require local verification.

## 📚 Documentation

| Document | Description |
|---|---|
| [`RUN_ON_YOUR_LAPTOP.md`](RUN_ON_YOUR_LAPTOP.md) | Installation, startup, demonstration, and troubleshooting |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System architecture |
| [`docs/MDP.md`](docs/MDP.md) | Optimization formulation and value iteration |
| [`docs/ML.md`](docs/ML.md) | Forecasting models and evaluation |
| [`docs/CHARGER_SCORING.md`](docs/CHARGER_SCORING.md) | Charging Opportunity Score |
| [`docs/SIMULATION.md`](docs/SIMULATION.md) | Simulation methodology and policy comparison |
| [`docs/API.md`](docs/API.md) | Backend API reference |
| [`docs/TESTING.md`](docs/TESTING.md) | Test results and verification |
| [`docs/VIVA_GUIDE.md`](docs/VIVA_GUIDE.md) | Project viva preparation |
| [`docs/SYNOPSIS_TRACEABILITY.md`](docs/SYNOPSIS_TRACEABILITY.md) | Project objectives mapped to implementation |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | Known limitations and future work |

## 📁 Repository Structure

```text
ev-optigrid/
├── backend/          # FastAPI backend, services, models and database
├── frontend/         # Next.js user interface
├── optimization/     # MDP, value iteration, battery and station optimization
├── ml/               # Forecasting models
├── simulation/       # Fleet simulation and policy evaluation
├── tests/            # Backend, ML, optimization and simulation tests
├── docs/             # Technical documentation
├── setup.bat         # Windows setup
├── start.bat         # Windows startup
├── setup.sh          # macOS/Linux setup
└── start.sh          # macOS/Linux startup
```

## 🔮 Future Improvements

- Integration with verified real-time charging station, tariff, and grid data.
- More extensive forecasting evaluation on real-world datasets.
- Production-ready persistent database and deployment configuration.
- Additional real-world route, traffic, and charging-network integrations.

---

**EV-OptiGrid** — Smarter charging decisions through machine learning, optimization, and simulation.

