# AI Workplace

> **Enterprise AI Workplace for ERPNext — Secure, Deterministic, Knowledge-Aware, and Extensible**

AI Workplace is an enterprise-grade AI application built on the **Frappe Framework** and designed to provide employees and organizations with a secure natural-language interface to HR and workplace services powered by **ERPNext/Frappe HR**.

The system combines deterministic business logic, controlled AI tools, enterprise knowledge retrieval, role-based authorization, and optional LLM capabilities to provide intelligent workplace assistance without giving the AI unrestricted access to the ERP system.

---

## Overview

AI Workplace is designed around a simple principle:

> **The ERP system remains the source of truth. AI is an interface and reasoning layer — not the system of record.**

Employees should be able to ask questions and perform supported workplace tasks using natural language without needing to navigate through multiple ERPNext screens.

Examples:

```text
"What is my remaining annual leave?"

"When is my next approved leave?"

"Show my attendance summary for August."

"How many casual leaves do I have remaining?"

"How do I apply for maternity leave?"

"What documents are required for employee onboarding?"

"Show me the HR policy for remote work."

"Submit a leave application for next Monday."
```

Depending on the request, AI Workplace determines whether the query should be handled by:

* deterministic application logic
* a controlled ERP tool
* the knowledge layer
* an LLM
* or a combination of these components

The LLM is **never treated as the authority for authorization or business rules**.

---

# Core Architecture Principles

AI Workplace follows several architectural principles.

### 1. ERPNext is the source of truth

Employee, attendance, leave, payroll, organizational, and transactional data remain inside ERPNext/Frappe.

AI Workplace does not replace ERPNext as the authoritative business system.

### 2. Authorization never belongs to the LLM

The model does not decide whether a user is allowed to access a record.

Authorization is enforced by the application and ERPNext permission system.

### 3. Business logic remains deterministic

Rules such as:

* leave balance calculation
* employee access
* approval requirements
* document permissions
* workflow transitions
* attendance calculations
* payroll-related access

are handled by deterministic application logic.

### 4. The LLM does not receive unrestricted ERP access

The model cannot arbitrarily query the database or execute arbitrary ERP operations.

Instead, it interacts with a controlled set of application-defined tools.

### 5. Use AI only when AI adds value

Not every query requires an LLM.

Simple, deterministic requests should be handled directly by application logic.

For example:

```text
User:
"What is my leave balance?"

        ↓

Intent detection

        ↓

Leave Balance Tool

        ↓

ERPNext

        ↓

Deterministic Response
```

There is no reason to spend an LLM call generating an answer that the application can safely produce itself.

---

# Key Features

## Employee AI Assistant

Employees can interact with workplace services using natural language.

Supported use cases can include:

* Leave balance
* Leave applications
* Attendance information
* Employee information
* Holiday information
* HR policies
* Company procedures
* Onboarding information
* Payroll-related information
* Workplace FAQs
* HR document retrieval
* General workplace assistance

---

## Intelligent Request Routing

AI Workplace classifies incoming requests before deciding how they should be processed.

A request may be routed to:

```text
                    User Request
                         │
                         ▼
                 Request Router
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
     Deterministic     Tool          Knowledge
        Logic         Execution        Search
          │              │              │
          └──────────────┼──────────────┘
                         │
                         ▼
                  Optional LLM
                         │
                         ▼
                  Final Response
```

This reduces unnecessary model usage while improving reliability and cost efficiency.

---

# Deterministic vs AI Processing

AI Workplace intentionally separates deterministic operations from AI reasoning.

### Deterministic operations

Examples:

* Leave balance
* Attendance summary
* Employee information
* Holiday lookup
* Document status
* Workflow status
* Permission checks
* Transaction creation
* Validation

These operations should preferably use application logic and tools rather than an LLM.

### AI-assisted operations

Examples:

* Understanding ambiguous natural language
* Summarizing HR policies
* Answering questions from organizational knowledge
* Explaining complex HR procedures
* Combining information from multiple knowledge sources
* Conversational assistance
* Generating human-friendly explanations

This architecture provides a balance between:

**Reliability + Security + Cost Efficiency + Intelligence**

---

# Knowledge Layer

An AI assistant is only as useful as the knowledge available to it.

AI Workplace therefore includes a dedicated knowledge architecture for organizational information.

Knowledge can include:

* HR policies
* Employee handbooks
* SOPs
* Leave policies
* Attendance policies
* Payroll policies
* Benefits information
* Onboarding documentation
* Company procedures
* Department documentation
* FAQs
* ERPNext/Frappe documentation
* Internal organizational knowledge

The knowledge pipeline is responsible for:

```text
Documents
   │
   ▼
Ingestion
   │
   ▼
Parsing
   │
   ▼
Chunking
   │
   ▼
Metadata
   │
   ▼
Embeddings
   │
   ▼
Vector / Search Index
   │
   ▼
Retrieval
   │
   ▼
AI Response
```

Knowledge retrieval is separated from transactional ERP access.

This prevents organizational documentation from being mixed indiscriminately with sensitive transactional data.

---

# Controlled Tool Architecture

AI Workplace uses application-defined tools to interact with ERPNext.

Instead of allowing the LLM to execute arbitrary database queries, the system exposes controlled operations such as:

```text
get_employee_info
get_leave_balance
get_leave_history
get_attendance_summary
get_holiday_list
get_salary_information
create_leave_application
get_hr_policy
search_knowledge
```

Each tool is responsible for:

1. validating input
2. validating the authenticated user
3. checking authorization
4. executing the operation
5. validating the result
6. returning structured data

The LLM receives the result rather than unrestricted ERP/database access.

---

# Security Architecture

Security is a first-class component of AI Workplace.

The system follows a defense-in-depth approach.

```text
User
 │
 ▼
Authentication
 │
 ▼
Session / Identity
 │
 ▼
Authorization
 │
 ▼
Request Validation
 │
 ▼
Tool Permission Guard
 │
 ▼
ERPNext Permission Layer
 │
 ▼
Controlled ERP Operation
 │
 ▼
Sanitized Result
 │
 ▼
Optional LLM
```

### Security principles

* No unrestricted database access for the LLM
* No LLM-controlled authorization
* Role-based access control
* User-scoped ERP data access
* Tool-level permission checks
* Input validation
* Output validation
* Sensitive-field protection
* Audit logging
* Rate limiting
* Session controls
* Prompt-injection defenses
* Controlled write operations

---

# Write Operations

Read operations and write operations are treated differently.

A read request such as:

```text
"What is my leave balance?"
```

can be executed through a controlled read tool.

A write request such as:

```text
"Apply for leave from September 10 to September 12."
```

requires additional validation.

Typical flow:

```text
User Request
     │
     ▼
Intent Detection
     │
     ▼
Tool Selection
     │
     ▼
Permission Check
     │
     ▼
Input Validation
     │
     ▼
Confirmation
     │
     ▼
ERPNext Transaction
     │
     ▼
Audit Log
```

The AI does not directly mutate ERPNext data.

---

# HR Knowledge and Services

AI Workplace is primarily designed around workplace and HR use cases.

Potential service areas include:

### Employee Services

* Employee profile
* Department
* Designation
* Joining information
* Employment information

### Leave Management

* Leave balance
* Leave history
* Leave status
* Leave policy
* Leave application
* Leave cancellation
* Holiday information

### Attendance

* Attendance summary
* Missing attendance
* Attendance history
* Working days
* Late/early information

### Payroll

Where permissions allow:

* Salary information
* Salary slip information
* Payroll-related FAQs
* Payroll policies

### HR Policies

Employees can ask questions such as:

```text
"What is the annual leave policy?"

"How many casual leaves can I take?"

"What is the procedure for requesting remote work?"

"What documents are required for onboarding?"
```

Answers should be grounded in the organization's approved knowledge sources.

---

# WhatsApp Integration

AI Workplace can be extended to provide HR services through messaging platforms such as WhatsApp.

The same controlled backend can serve multiple channels:

```text
                    AI Workplace
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ▼                ▼                ▼
      Web UI          WhatsApp         Other APIs
        │                │                │
        └────────────────┼────────────────┘
                         ▼
                  Request Processing
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
       ERPNext Tools            Knowledge
             │                       │
             └───────────┬───────────┘
                         ▼
                     AI Layer
```

This allows employees to access supported HR services without opening ERPNext directly.

---

# Agent Architecture

AI Workplace is designed to support specialized agents where they provide meaningful value.

Examples include:

* HR Assistant
* Knowledge Assistant
* Leave Assistant
* Attendance Assistant
* Employee Services Assistant
* Policy Assistant
* Administrative Assistant

Agents should operate within defined capabilities and permissions rather than receiving unrestricted access to the entire system.

---

# Observability and Auditability

Enterprise AI systems must be observable.

AI Workplace is designed to track important operational information such as:

* requests
* sessions
* tool executions
* response times
* model usage
* token consumption
* errors
* failures
* security events
* knowledge retrieval
* AI decisions
* write operations

This enables administrators to understand:

```text
What happened?
Why did it happen?
Which tool was called?
What data was accessed?
Was AI involved?
How much did the request cost?
Did the operation succeed?
```

---

# Architecture

High-level architecture:

```text
                         ┌──────────────────────┐
                         │        User          │
                         └──────────┬───────────┘
                                    │
                     ┌──────────────┴──────────────┐
                     │                             │
                     ▼                             ▼
                 Web UI                         WhatsApp
                     │                             │
                     └──────────────┬──────────────┘
                                    │
                                    ▼
                         ┌──────────────────────┐
                         │   AI Workplace API   │
                         └──────────┬───────────┘
                                    │
                         ┌──────────▼───────────┐
                         │ Request Orchestrator │
                         └──────────┬───────────┘
                                    │
               ┌────────────────────┼────────────────────┐
               │                    │                    │
               ▼                    ▼                    ▼
        Deterministic          Tool Layer          Knowledge
           Logic                                      Layer
               │                    │                    │
               │                    ▼                    ▼
               │               ERPNext/Frappe       Documents
               │                    │                Vector Index
               │                    │                    │
               └────────────────────┼────────────────────┘
                                    │
                                    ▼
                              Optional LLM
                                    │
                                    ▼
                              Final Response
```

---

# Technology Stack

AI Workplace is built around the Frappe ecosystem.

| Component             | Technology                               |
| --------------------- | ---------------------------------------- |
| ERP / Source of Truth | ERPNext                                  |
| Application Framework | Frappe Framework                         |
| HR                    | Frappe HR / ERPNext HR                   |
| Backend               | Python                                   |
| Database              | MariaDB                                  |
| AI Layer              | Configurable LLM provider                |
| Knowledge             | RAG / Vector Search                      |
| Messaging             | WhatsApp integration                     |
| Authentication        | ERPNext/Frappe                           |
| Authorization         | ERPNext/Frappe permissions               |
| Deployment            | Frappe Bench / Production infrastructure |

---

# Project Structure

The application follows the Frappe application structure.

```text
ai_workplace/
│
├── ai_workplace/
│   ├── api/
│   ├── ai/
│   ├── agents/
│   ├── tools/
│   ├── knowledge/
│   ├── services/
│   ├── security/
│   ├── integrations/
│   ├── doctype/
│   └── utils/
│
├── doc/
│
├── pyproject.toml
├── README.md
└── license.txt
```

The exact structure may evolve as the application grows.

---

# Installation

AI Workplace is a Frappe application.

First install a compatible Frappe/ERPNext environment.

Then obtain the application:

```bash
bench get-app https://github.com/azfar3/ai_workplace
```

Install it on the required site:

```bash
bench --site <site-name> install-app ai_workplace
```

Run migrations:

```bash
bench --site <site-name> migrate
```

Start the development environment:

```bash
bench start
```

---

# Configuration

AI Workplace configuration should be environment-specific.

Typical configuration areas include:

* ERPNext site
* AI provider
* LLM model
* API credentials
* Embedding provider
* Vector database
* Knowledge sources
* WhatsApp credentials
* Rate limits
* AI usage limits
* Security policies

Sensitive credentials must never be committed to Git.

Use environment variables or the appropriate secure Frappe configuration mechanisms.

---

# Development

Clone the repository:

```bash
git clone https://github.com/azfar3/ai_workplace.git
```

Enter the application directory:

```bash
cd ai_workplace
```

For Frappe development, use a dedicated bench environment.

Install the application in development mode and run:

```bash
bench start
```

---

# Testing

The project should maintain automated tests for:

* authentication
* authorization
* tool permissions
* deterministic services
* knowledge retrieval
* AI routing
* prompt injection defenses
* input validation
* write operations
* ERPNext integration
* WhatsApp integration
* error handling

Run the Frappe test suite with:

```bash
bench --site <site-name> run-tests --app ai_workplace
```

---

# Production Considerations

Before deploying AI Workplace in a production environment, ensure:

* HTTPS is enabled
* API credentials are securely stored
* ERPNext permissions are correctly configured
* AI provider credentials are protected
* rate limits are enabled
* audit logging is enabled
* sensitive fields are protected
* database backups are configured
* knowledge sources are reviewed
* write operations require appropriate confirmation
* monitoring and alerting are configured
* AI usage and costs are monitored

AI Workplace should be deployed with the same security standards expected from other enterprise systems.

---

# Roadmap

The project is evolving toward a complete enterprise AI workplace platform.

Planned areas include:

* [ ] Expanded HR tools
* [ ] Enterprise knowledge ingestion
* [ ] Advanced RAG pipeline
* [ ] Multi-agent orchestration
* [ ] WhatsApp HR assistant
* [ ] Advanced authorization policies
* [ ] AI usage analytics
* [ ] Token and cost monitoring
* [ ] AI audit trails
* [ ] Administrative dashboard
* [ ] Knowledge management UI
* [ ] Automated knowledge refresh
* [ ] Improved prompt-injection protection
* [ ] Human-in-the-loop workflows
* [ ] Multi-channel workplace assistant
* [ ] Advanced employee self-service

---

# Design Philosophy

AI Workplace is not intended to be:

> "An LLM connected directly to an ERP database."

Instead, it is designed as:

> **A secure enterprise application where AI operates within deterministic business rules, controlled tools, organizational knowledge, and existing ERPNext permissions.**

This distinction is fundamental to the architecture.

The goal is to make AI:

**Useful without being unrestricted.**

**Intelligent without being authoritative.**

**Conversational without compromising security.**

**Flexible without bypassing business rules.**

---

# Contributing

Contributions, improvements, bug reports, and architectural suggestions are welcome.

Before submitting a pull request:

1. Follow the project's coding conventions.
2. Add or update tests where appropriate.
3. Ensure security boundaries are preserved.
4. Do not introduce unrestricted database access for AI components.
5. Document new tools, agents, or integrations.
6. Ensure sensitive credentials are not committed.

---

# License

AI Workplace is released under the **MIT License**.

See [`license.txt`](./license.txt) for details.

---

# Project Status

AI Workplace is an actively evolving project focused on building a secure and practical enterprise AI layer for ERPNext/Frappe-based organizations.

The architecture is intentionally designed to evolve from a basic AI assistant into a broader **AI Workplace platform** supporting employee self-service, organizational knowledge, controlled automation, analytics, and multi-channel interaction.
