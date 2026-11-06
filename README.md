
# KubeCoach

### Project ID: SJ-58
### Theme: Developer Tools

## About
KubeCoach explains Kubernetes objects and kubectl
commands in simple English using official Kubernetes
documentation.

## Target Users
Final-year IT students preparing for DevOps interviews.

## Problem
Kubernetes documentation can be difficult for beginners
to understand. KubeCoach makes the concepts easier.

## Data Source
https://kubernetes.io/docs/concepts/

## Day 1 Progress
- Created day01_intro.py
- Created day01_menu.py
- Practised Python variables, input and f-strings
- Practised conditions and loops

## Day 2 Progress
- Added 18 real Kubernetes records from the official documentation.
- Practised list and dictionary based data handling.
- Added keyword search and category counting.
- Organised reusable functions in `app/records.py`.
- Added a modular `app/` and `data/` project structure.
- Added a CLI for searching and viewing Kubernetes records.

## How to Run

From the `GenAI` directory:

```text
python -m app.cli
```

The project uses only Python's standard library, so no package installation is
required. A virtual environment can be created locally with:

```text
python -m venv .venv
```
