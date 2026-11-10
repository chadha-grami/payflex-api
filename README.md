# PayFlex API - Advanced CI/CD pipeline

Node.js payment API + GitHub Actions pipeline with 3 test levels, SonarQube, Gitleaks
(confidentiality rate) and a scripted Quality Gate (warning vs critical, fail fast).

Pipeline: secrets-source -> unit-tests -> sonar -> integration-tests -> performance-tests -> secrets-artifacts -> report -> deploy

Local run:  npm install && bash scripts/local_check.sh [latency_ms]
Demo perf failure: Actions > "PayFlex CI/CD" > Run workflow > simulate_latency_ms = 600
Demo leak:  bash scripts/demo_leak.sh
Report:     pip install reportlab && python3 report/build_report.py --name "Your NAME" --repo "<repo url>"
