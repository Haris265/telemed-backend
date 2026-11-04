# Role
You are a Senior Software Architect and a highly experienced Platform Engineer.

# Objective
Analyze the existing codebase thoroughly and prepare a detailed implementation plan for an Analytics feature.

The goal is to identify all useful analytics and statistics that can be generated from the existing codebase and displayed on the dashboards of the following user roles:

- Super Admin
- Clinic Admin
- Doctor

The analytics plan must be based on the current implementation, existing data models, database structure, relationships, APIs, business logic, and other relevant parts of the codebase.

## 1. Analyze the Existing Codebase

Before preparing the implementation plan, thoroughly inspect the current codebase to understand:

- Existing architecture and project structure.
- Database schema, models, entities, and their relationships.
- Existing clinic, doctor, and appointment-related functionality.
- Existing APIs, services, queries, and business logic that can provide analytics data.
- Current dashboard implementations for Super Admin, Clinic Admin, and Doctor, if available.
- Existing data fields that can be used to calculate meaningful statistics.
- Any existing limitations in the current implementation that may affect analytics.

Do not assume that a feature, data field, relationship, or functionality exists without verifying it in the codebase.

## 2. Identify All Possible Analytics

Based on the existing code, identify all useful analytics and statistics that can be implemented with the data currently available.

Prioritize analytics that can be implemented easily by reusing existing data, models, relationships, APIs, and business logic.

Clearly distinguish between:

1. Analytics that can be implemented directly using existing data.
2. Analytics that require additional calculations or aggregation logic.
3. Analytics that require changes to the existing codebase or data structure.
4. Analytics that cannot currently be calculated because the required data is missing.

Do not invent additional data or assume that missing information is available.

## 3. Super Admin Analytics

Define the analytics that should be available to the Super Admin at the platform level.

For example, if the required data exists in the current codebase, the Super Admin dashboard should be able to display:

- Total number of clinics.
- Total number of doctors.
- Total number of appointments across the platform.
- Clinic-level appointment statistics.
- Doctor-level appointment statistics.
- Each clinic's contribution to the platform's total appointments.
- Each doctor's contribution to their clinic's total appointments.
- Comparisons between clinics and doctors based on appointment volume.

The Super Admin should also be able to select a specific clinic and inspect its detailed analytics.

After selecting a clinic, the Super Admin should be able to view the available clinic-level statistics, including:

- Total doctors associated with that clinic.
- Total appointments associated with that clinic.
- Appointment statistics for individual doctors within the clinic.
- The contribution of each doctor to the clinic's total appointment volume.
- Other useful statistics supported by the existing codebase.

Explain how the Super Admin can move from high-level platform statistics to clinic-level and doctor-level analytics.

## 4. Clinic Admin Analytics

Define the analytics that should be available to a Clinic Admin within the scope of their own clinic.

The Clinic Admin should be able to understand the clinic's overall performance and inspect individual doctors' appointment statistics.

For example, where the existing data supports these calculations, the dashboard should show:

- Total doctors in the clinic.
- Total appointments associated with the clinic.
- Appointment statistics for individual doctors.
- Each doctor's contribution to the clinic's total appointments.
- Which doctors have the highest and lowest appointment volumes.
- Other useful clinic-level and doctor-level statistics available from the current codebase.

The Clinic Admin's analytics must remain restricted to their own clinic. They must not be able to access another clinic's analytics through the dashboard, API, or any other available interface.

Verify how the current authorization and data-access logic works before defining the implementation.

## 5. Doctor Analytics

Inspect the existing codebase to determine which analytics can be provided to individual doctors.

Define the useful statistics that can be displayed on the Doctor dashboard based on the data available to that doctor.

Do not assume that every doctor-related statistic is supported. Explain which metrics are possible using the existing implementation and which require additional data or functionality.

## 6. Doctor Popularity and Appointment Contribution

A key requirement is to identify which doctors are receiving the highest number of appointments within a clinic.

For example, suppose a clinic has 100 appointments in total:

- Doctor A has 50 appointments.
- Doctor B has 30 appointments.
- Doctor C has 20 appointments.

If these numbers are supported by the actual appointment data, the analytics should be able to show each doctor's appointment volume and percentage contribution to the clinic's total appointments.

The percentage contribution should be calculated using the relevant appointment totals available in the existing system.

Explain how the system can identify doctors with relatively high or low appointment volumes and how this information can be presented in the dashboard.

**Important:** Appointment volume can be used as an indicator of appointment activity or demand, but do not automatically equate it with actual revenue. Revenue-related analytics must only be proposed as directly calculable when the existing codebase contains the necessary financial data and business logic. If revenue data is unavailable, explicitly state this limitation.

## 7. Dashboard Analytics Structure

Prepare a clear structure for the analytics dashboards for all three roles.

Explain:

- Which statistics should appear at the top level of each dashboard.
- Which statistics should be available in detailed views.
- How users should navigate from summary statistics to more detailed analytics.
- Which clinic-level and doctor-level comparisons are useful.
- Which metrics should be displayed as summary cards, tables, charts, or other appropriate dashboard elements.

Use practical examples wherever necessary to explain how each metric would work.

Do not prescribe UI elements or interactions as existing functionality unless you have verified them in the codebase. Clearly identify proposed dashboard changes as new implementation work.

## 8. Detailed Implementation Plan

Prepare a step-by-step implementation plan based on the current codebase.

For every proposed analytics metric or feature, explain:

- What the metric represents.
- Why it is useful.
- What existing data is required.
- Where that data currently exists in the codebase.
- How the metric can be calculated.
- Which existing models, relationships, APIs, services, or queries can be reused.
- Whether new backend logic or database changes are required.
- Which dashboard and user role should display it.
- Any relevant access-control or data-visibility requirements.
- Any limitations or dependencies that could affect implementation.

When referring to the existing code, provide the actual file paths, class names, model names, function names, API endpoints, or other relevant identifiers found during the inspection.

Do not fabricate file paths, class names, methods, endpoints, or database fields.

If a required implementation detail cannot be verified, explicitly identify it as an item that needs further investigation.

## 9. Mermaid Diagrams

Use Mermaid diagrams wherever they help explain the architecture, data relationships, analytics flow, or implementation process.

For example, include diagrams when useful to explain:

- How data flows from the database through backend logic to the dashboards.
- How the Super Admin navigates from platform-level analytics to clinic-level and doctor-level analytics.
- How clinic-level and doctor-level appointment statistics are calculated and displayed.
- The proposed implementation workflow.

Every diagram must represent the actual architecture or a clearly labelled proposed design. Do not present an assumed architecture as an existing implementation.

## 10. Prioritization and Implementation Phases

Organize the implementation plan according to what can be achieved most easily and effectively using the existing codebase.

Clearly separate:

- Phase 1: Analytics that can be implemented using existing data and functionality with minimal changes.
- Phase 2: Analytics that require additional backend logic, queries, aggregation, or dashboard changes.
- Phase 3: Analytics that depend on missing data, database changes, or additional functionality.

Adjust these phases according to your actual findings. Do not force a feature into a phase if the codebase does not support it.

For each phase, explain the required work, dependencies, and expected outcome.

# Important Instructions

1. Thoroughly inspect the existing codebase before preparing the plan.
2. Base every recommendation on verified code or clearly label it as a proposed change.
3. Do not invent features, data, business rules, architecture, or implementation details.
4. Do not modify the codebase or start implementing the feature. The current task is to analyze the code and produce a detailed implementation plan only.
5. Reuse existing models, relationships, APIs, services, and business logic wherever practical.
6. Avoid unnecessary complexity and unnecessary changes to the existing architecture.
7. Do not assume that appointment counts, completed appointments, cancelled appointments, active doctors, or revenue are interchangeable. Verify the existing business rules and data definitions before proposing calculations.
8. Explain any assumptions, missing information, technical limitations, or unresolved questions explicitly.
9. Use clear, simple Roman Urdu throughout the plan so that the implementation details are easy to understand.
10. Include practical examples wherever they improve understanding.
11. Include Mermaid diagrams wherever they materially improve clarity.
12. Make the plan detailed enough that a developer can use it as a practical guide for implementing the analytics feature without having to guess the intended behavior.

# Expected Deliverable

Produce a comprehensive, codebase-specific Analytics Implementation Plan in simple Roman Urdu.

The final document should include:

1. Executive summary.
2. Existing codebase and architecture analysis.
3. Relevant database models, relationships, APIs, and business logic.
4. Analytics inventory: all useful metrics supported by the current code.
5. Separate analytics requirements for Super Admin, Clinic Admin, and Doctor.
6. Detailed explanation and calculation examples for each proposed metric.
7. Clinic and doctor appointment contribution analysis.
8. Proposed dashboard structure and navigation.
9. Relevant Mermaid diagrams.
10. File-by-file implementation guidance based on verified code.
11. Required backend, database, API, and frontend changes.
12. Data access, authorization, and clinic-level isolation considerations.
13. Phased implementation plan, prioritized by feasibility and effort.
14. Limitations, dependencies, and unresolved questions.

The final objective is to provide a realistic and actionable implementation plan that maximizes the analytics available from the current codebase while avoiding unnecessary development work and unsupported assumptions.