# 🛡️ SupplyShield-AI

**AI-Powered Supply Chain Risk Management Platform**

SupplyShield-AI is a full-stack Flask application that leverages Google Gemini AI to analyze supplier risk profiles, automate compliance workflows, and generate actionable remediation strategies for supply chain managers.

---

## 🚀 Features

- **CSV Supplier Ingestion** — Upload supplier data via CSV with intelligent column mapping and auto-aggregation
- **AI Risk Analysis** — Automated hazard scoring and risk classification powered by Google Gemini
- **Live News Risk Integration** — Fetches real-time news via NewsAPI to detect supplier violations, shortages, and fraud
- **Interactive Dashboard** — Real-time charts (bar, pie, heatmap, treemap, network graph) for fleet-wide risk visibility
- **Compliance Chat** — Ask natural language questions about supplier risks and receive AI-generated answers
- **GitLab Integration** — Auto-create compliance issue tickets for high-risk suppliers via GitLab API
- **Email Alerts** — Send compliance warning emails to suppliers with audit logging
- **PDF Report Generation** — Export executive-grade compliance audit reports (Premium)
- **CSV Export** — Download filtered supplier data as CSV spreadsheets
- **Scan Snapshots** — Save, load, and manage historical scan snapshots
- **Tiered Access Control** — Free and Premium tiers with Admin management panel
- **Email Verification** — Account verification via Resend email service

---

## 🏗️ Architecture

```
SupplyShield-ai/
├── app.py                    # Main Flask application (routes, API endpoints)
├── db_config.py              # MongoDB Atlas connection (lazy proxy)
├── models.py                 # Data models (user, supplier, audit log)
├── requirements.txt          # Python dependencies
├── Procfile                  # Heroku deployment config
├── LICENSE                   # MIT License
├── .env                      # Environment variables (not tracked)
│
├── MCP_tools/                # Model Context Protocol integrations
│   ├── email_tool.py         #   Resend email sending
│   ├── gitlab_tool.py        #   GitLab issue creation
│   └── mongodb_toll.py       #   MongoDB query/write tools
│
├── utils/                    # Utility modules
│   ├── auth_helpers.py       #   Authentication, hashing, email verification
│   ├── background_worker.py  #   Background AI analysis & chat engine
│   └── email_validation.py   #   Email format validation
│
├── templates/                # Jinja2 HTML templates
│   ├── base.html             #   Base layout
│   ├── landing.html          #   Public landing page
│   ├── dashboard.html        #   Main dashboard with upload & charts
│   ├── admin.html            #   Admin user management panel
│   ├── premium.html          #   Premium features page
│   ├── supplier_detail.html  #   Individual supplier detail view
│   ├── auth/                 #   Login & registration templates
│   └── partials/             #   Reusable template components
│
├── static/                   # Frontend assets
│   ├── css/style.css         #   Global styles
│   ├── js/main.js            #   Dashboard JavaScript logic
│   └── img/                  #   Images and icons
│
└── sample_data/              # Sample datasets
    └── suppliers_sample.csv  #   Example supplier CSV file
```

---

## ⚙️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Flask, Python 3.10+ |
| **Database** | MongoDB Atlas (via PyMongo) |
| **AI Engine** | Google Gemini (`google-genai`) |
| **News Intelligence** | NewsAPI (`newsapi-python`) |
| **Authentication** | Flask-Login, Flask-Bcrypt, Flask-WTF |
| **Email** | Resend API |
| **Issue Tracking** | GitLab API (`python-gitlab`) |
| **PDF Generation** | ReportLab |
| **Data Processing** | Pandas, NumPy |
| **Deployment** | Heroku / Gunicorn |

---

## 📋 Prerequisites

- Python 3.10 or higher
- A [MongoDB Atlas](https://www.mongodb.com/atlas) account and cluster
- A [Google AI Studio](https://aistudio.google.com/) API key (Gemini)
- A [NewsAPI](https://newsapi.org/) API key (for live supplier news risk analysis)
- A [Resend](https://resend.com/) API key (for email features)
- A [GitLab](https://about.gitlab.com/) account with API access (for ticket features)

---

## 🛠️ Installation & Setup

### 1. Clone the repository

```bash
git clone https://github.com/taranjotsinghW28/-SupplyShield-AI.git
cd SupplyShield-AI
```

### 2. Create a virtual environment

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
# MongoDB Atlas
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster-url>/SupplyShieldDB?retryWrites=true&w=majority

# Flask
SECRET_KEY=your-secret-key-here

# Google Gemini AI
GEMINI_API_KEY=your-gemini-api-key

# NewsAPI (for live supplier news risk analysis)
NEWS_API_KEY=your-newsapi-key

# Resend Email
RESEND_API_KEY=your-resend-api-key

# GitLab (optional)
GITLAB_PRIVATE_TOKEN=your-gitlab-token
GITLAB_PROJECT_ID=your-project-id
```

### 5. Run the application

```bash
python app.py
```

The application will start at **http://localhost:5000**.

A default admin account is automatically created:
- **Username:** `admin`
- **Password:** `Admin@2026`

> ⚠️ Change the admin password immediately in production.

---

## 🐳 Deployment

### Heroku

```bash
heroku create your-app-name
git push heroku main
```

The included `Procfile` configures Gunicorn for production deployment.

### Docker (manual setup)

```bash
gunicorn app:app --bind 0.0.0.0:5000
```

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Landing page |
| GET/POST | `/auth/register` | User registration |
| GET/POST | `/auth/login` | User login |
| GET | `/auth/logout` | User logout |
| GET | `/verify/<token>` | Email verification |
| GET | `/dashboard` | Main dashboard |
| GET | `/admin` | Admin panel (Admin only) |
| POST | `/api/upload-csv` | Upload supplier CSV |
| POST | `/api/scan-cancel` | Cancel active scan |
| POST | `/api/scan-clear` | Clear cancel flag |
| POST | `/api/scan-clear-and-return` | Clear all supplier data |
| POST | `/api/scan-save` | Save scan snapshot |
| GET | `/api/scan-load/<id>` | Load saved snapshot |
| DELETE | `/api/scan-delete/<id>` | Delete snapshot |
| GET | `/api/scan-history` | Get scan history |
| GET | `/api/suppliers-list` | List all suppliers |
| GET | `/supplier/<id>` | Supplier detail page |
| POST | `/api/chat-compliance` | AI compliance chat |
| POST | `/api/analytics/dashboard-charts` | Chart data |
| POST | `/api/analytics/draft-ai-ticket` | AI ticket drafting (Premium) |
| POST | `/api/analytics/dispatch-bulk-remediation` | Create GitLab ticket |
| POST | `/api/analytics/dispatch-all-high-risk` | Batch dispatch all high-risk |
| GET | `/api/analytics/get-email-recipients` | Get high-risk email contacts |
| POST | `/api/analytics/draft-ai-email` | AI email drafting (Premium) |
| POST | `/api/analytics/send-alert-email` | Send compliance email |
| GET | `/api/export/suppliers-csv` | Export suppliers as CSV |
| GET | `/api/export/compliance-pdf` | Export audit PDF (Premium) |

---

## 🗺️ Future Roadmap

- **Predictive Analytics:** Transition from static hazard scoring to time-series forecasting to predict supplier failure before it happens based on economic trends.
- **Real-time News Integration:** Implement a web-scraping agent to pull real-time news regarding supplier regions (e.g., natural disasters, strikes) to update risk scores dynamically.
- **Automated Remediation Workflows:** Add "One-Click Mitigation" where the AI suggests and executes supply-rerouting paths based on the hazard score.
- **API-First Design:** Expose the risk-analysis engine as a standalone REST API so other organizations can plug their own datasets into SupplyShield's intelligence.

---

## ⚠️ Challenges Faced

- **Data Normalization:** Ingesting supplier CSVs from different companies meant dealing with inconsistent formatting. I solved this by building an intelligent mapping layer that uses fuzzy string matching and LLM-assisted column detection.
- **API Authentication:** Transitioning to modern authorization protocols (the AQ. key structure) required a complete refactor of how the application handshakes with Google AI Studio.
- **Scalability:** Maintaining low-latency AI responses with large supplier datasets was a challenge. I implemented caching for frequent risk queries to reduce the number of redundant API calls, significantly improving dashboard load speeds.
- **Agentic Orchestration:** Ensuring the AI agent reliably triggers the GitLab API and Resend email service without hallucinating task parameters required strict system-prompt engineering and validation layers.

---

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.