# Multi-Clinic Parent Chatbot

## Product Concept, Current Architecture, Proposed Architecture, and End-to-End User Journey

**Document purpose:** Explain the proposed multi-clinic parent chatbot
clearly to product, engineering, and business teams. This document
describes the concept and expected behavior at a high level; it does not
assume that implementation details have already been decided.

------------------------------------------------------------------------

## 1. Executive Summary

The current platform supports multiple clinics, but the chatbot
experience is clinic-specific: each clinic has its own chatbot, and that
chatbot handles the clinic's doctors, available appointment slots,
booking, and cancellation.

The proposal is to add a **Parent Chatbot** that provides one common
entry point for users who want to explore and book appointments across
multiple registered clinics. A user will start a conversation, see the
available clinics, select a clinic, review the doctors and their
specialties, choose a doctor and an available slot, and then book an
appointment. The parent experience should also support appointment
cancellation by reusing the existing cancellation capability.

**This is an addition to the product, not a replacement. No existing
feature is being removed.**

The product will support both experiences:

1.  **Clinic-specific chatbot --- Premium feature:** A dedicated chatbot
    experience for an individual clinic.
2.  **Parent chatbot --- Multi-clinic experience:** One central chatbot
    through which a user can discover and interact with multiple
    registered clinics.

The key implementation principle is to **reuse the existing appointment
workflows wherever possible**. The parent chatbot should provide the
clinic-discovery and selection layer, then pass a validated clinic
context into the existing doctor, slot, booking, and cancellation
workflows. This avoids building a second, separate appointment system
and reduces the risk of the two experiences behaving differently.

------------------------------------------------------------------------

## 2. Goals and Scope

### Goals

-   Provide one chatbot entry point for multiple registered clinics.
-   Allow users to discover and select a clinic before viewing its
    doctors.
-   Show doctors belonging to the selected clinic, including their
    specialties.
-   Show available slots for the selected doctor.
-   Support appointment booking and cancellation in the parent chatbot.
-   Preserve the current clinic-specific chatbot as a premium feature.
-   Reuse the current booking and cancellation logic where practical.
-   Ensure every doctor, slot, appointment, and cancellation action
    remains associated with the correct clinic.

### Out of scope for this proposal

This document does not require or propose removing the current
clinic-specific chatbot. It also does not assume that the parent chatbot
will automatically merge clinic data into one shared database or replace
clinic-level administration. The parent chatbot is a shared user
experience over the registered clinics; each clinic remains a distinct
entity with its own doctors and availability.

Specific implementation details---such as authentication, payment,
notification channels, appointment ownership rules, and exact API
contracts---should be confirmed against the existing product before
development.

------------------------------------------------------------------------

## 3. Current Architecture: Clinic-Specific Chatbots

### 3.1 Current concept

Today, each clinic has its own chatbot experience. A user entering a
clinic's chatbot is already operating within that clinic's context. The
chatbot can then show that clinic's doctors, display their available
slots, and use the existing appointment booking and cancellation
functionality.

The platform may have many clinics, and each clinic may have multiple
doctors. Each doctor may have multiple appointment slots.

### 3.2 Current hierarchy

``` mermaid
flowchart TD
    A[Platform Admin] --> C1[Clinic A]
    A --> C2[Clinic B]
    A --> C3[Clinic C]

    C1 --> A1[Clinic A Chatbot]
    C2 --> B1[Clinic B Chatbot]
    C3 --> C1B[Clinic C Chatbot]

    C1 --> D1[Doctor A1]
    C1 --> D2[Doctor A2]
    C2 --> D3[Doctor B1]
    C2 --> D4[Doctor B2]
    C3 --> D5[Doctor C1]

    D1 --> S1[Available Slots]
    D2 --> S2[Available Slots]
    D3 --> S3[Available Slots]
    D4 --> S4[Available Slots]
    D5 --> S5[Available Slots]
```

> **Reading the diagram:** The admin manages the platform-level clinic
> structure. Each clinic has its own chatbot experience and its own
> doctors. Each doctor's availability is represented by that doctor's
> slots. The exact administrative permissions and data relationships
> should follow the existing implementation.

### 3.3 Current clinic-specific booking flow

``` mermaid
flowchart TD
    U[User opens a specific clinic's chatbot] --> C[Clinic context is already known]
    C --> D[Show doctors for that clinic]
    D --> SP[Show doctor specialties and relevant details]
    SP --> DS[User selects a doctor]
    DS --> SL[Show that doctor's available slots]
    SL --> CH[User selects a slot]
    CH --> B[Existing booking workflow]
    B --> CF[Booking confirmation]

    U --> X[User requests cancellation]
    X --> V[Identify and validate the appointment]
    V --> CX[Existing cancellation workflow]
    CX --> CC[Cancellation confirmation]
```

### 3.4 What already exists and should be preserved

The existing clinic-specific chatbot is working and should remain
available. The current product already supports the core clinic-level
appointment journey:

-   A clinic-specific chatbot experience.
-   Doctors associated with a clinic.
-   Doctor appointment slots.
-   Appointment booking.
-   Appointment cancellation.

The proposed parent chatbot should not duplicate these capabilities
unnecessarily. It should reuse the existing, proven workflows wherever
possible.

------------------------------------------------------------------------

## 4. Proposed Change: One Parent Chatbot for All Clinics

### 4.1 The idea

Add one **Parent Chatbot** that can serve as the starting point for
users who have not yet chosen a clinic.

Instead of requiring a user to know which clinic chatbot to open, the
user opens the parent chatbot and sees the registered clinics available
through that experience. After selecting a clinic, the user sees only
the doctors associated with that clinic, including their specialties.
The user can then select a doctor, view available slots, and book an
appointment.

The parent chatbot is therefore a **multi-clinic discovery and routing
layer**. It is not a replacement for the clinic-level appointment
system.

### 4.2 Proposed hierarchy

``` mermaid
flowchart TD
    A[Platform Admin] --> P[Parent Chatbot: All Participating Clinics]

    P --> C1[Clinic A]
    P --> C2[Clinic B]
    P --> C3[Clinic C]

    C1 --> D1[Doctor A1]
    C1 --> D2[Doctor A2]
    C2 --> D3[Doctor B1]
    C2 --> D4[Doctor B2]
    C3 --> D5[Doctor C1]

    D1 --> S1[Doctor A1 Slots]
    D2 --> S2[Doctor A2 Slots]
    D3 --> S3[Doctor B1 Slots]
    D4 --> S4[Doctor B2 Slots]
    D5 --> S5[Doctor C1 Slots]

    C1 -. remains available as .-> CB1[Clinic A Premium Chatbot]
    C2 -. remains available as .-> CB2[Clinic B Premium Chatbot]
    C3 -. remains available as .-> CB3[Clinic C Premium Chatbot]
```

**Important:** The parent chatbot provides access to multiple clinics.
Each clinic still owns or is associated with its own doctors and
availability. Clinic-specific chatbots remain available as a separate
premium experience.

### 4.3 Two chatbot experiences will coexist

  -----------------------------------------------------------------------
  Capability              Parent chatbot          Clinic-specific chatbot
  ----------------------- ----------------------- -----------------------
  Intended audience       Users exploring         Users who want to
                          multiple clinics        interact with one
                                                  specific clinic

  Clinic context          User selects a clinic   Clinic is already known
                          during the conversation from the entry point

  Clinic discovery        Yes                     Not required for the
                                                  normal clinic-specific
                                                  journey

  Doctor list             Doctors for the         Doctors for that clinic
                          selected clinic         

  Doctor specialty        Shown with the relevant Shown with the relevant
                          doctor, where available doctor, where available

  Slot selection          Available slots for the Available slots for the
                          selected doctor         selected doctor

  Booking                 Reuse the existing      Existing workflow
                          booking workflow        remains available

  Cancellation            Reuse the existing      Existing workflow
                          cancellation workflow   remains available

  Product positioning     Shared multi-clinic     Premium,
                          experience              clinic-specific chatbot
                                                  experience

  Replaces the other      No                      No
  experience?                                     
  -----------------------------------------------------------------------

The exact commercial rules for the premium feature---such as which
clinics qualify and how access is enabled---remain a product/business
decision. The important product decision for this proposal is that the
clinic-specific chatbot is retained.

------------------------------------------------------------------------

## 5. Proposed Parent Chatbot User Journey

### 5.1 End-to-end flow

``` mermaid
flowchart TD
    U[User opens Parent Chatbot] --> W[Welcome message and available actions]
    W --> INT{What does the user want to do?}

    INT -->|Book appointment| CL[Fetch and display participating clinics]
    CL --> SC[User selects a clinic]
    SC --> DC[Fetch doctors for the selected clinic]
    DC --> SPEC[Display doctor names and specialties]
    SPEC --> SD[User selects a doctor]
    SD --> AV[Fetch that doctor's available slots]
    AV --> DATE[User chooses a suitable date and time]
    DATE --> VALID[Revalidate slot availability]
    VALID -->|Slot still available| BOOK[Call existing booking workflow]
    VALID -->|Slot no longer available| REFRESH[Refresh slots and ask user to choose again]
    REFRESH --> AV
    BOOK --> CONF[Show booking confirmation]

    INT -->|Cancel appointment| FIND[Identify the user's appointment using the existing supported process]
    FIND --> VERIFY[Validate appointment and cancellation eligibility]
    VERIFY --> CANCEL[Call existing cancellation workflow]
    CANCEL --> CCONF[Show cancellation confirmation]

    INT -->|Other question| HELP[Handle supported question or guide user to the right action]
```

### 5.2 Step-by-step explanation

**Step 1 --- User opens the parent chatbot**

The user enters through the central chatbot rather than through an
individual clinic chatbot. The chatbot explains that the user can select
a clinic and then book or manage an appointment.

**Step 2 --- Display available clinics**

The parent chatbot fetches the clinics that are registered and enabled
for the parent experience. Each clinic option should be
identifiable---for example, by clinic name and, if available, location
or branch information.

The chatbot should not show clinics that are inactive or not eligible
for this experience. The exact visibility rules must match the
platform's existing clinic status and access rules.

**Step 3 --- User selects a clinic**

The selected clinic becomes the active context for the booking journey.
The system should retain the clinic's stable internal ID, not rely only
on the clinic name shown in chat.

**Step 4 --- Display doctors and specialties**

The chatbot fetches doctors associated with the selected clinic. It
displays their names and specialties, where those details exist. If a
clinic has several doctors or several specialties, the user can compare
the relevant options before choosing.

Only doctors associated with the selected clinic should be returned for
this step.

**Step 5 --- User selects a doctor**

The parent chatbot records the selected doctor's ID and verifies that
the doctor belongs to the selected clinic. This prevents a user from
accidentally entering another clinic's booking flow.

**Step 6 --- Display available appointment slots**

The chatbot retrieves the selected doctor's available slots through the
existing availability mechanism or the appropriate existing service.
Only bookable slots should be offered.

**Step 7 --- User chooses a date and time**

The user selects a slot. Before finalizing the booking, the system
should revalidate availability because another user may have booked the
same slot while the conversation was in progress.

**Step 8 --- Book through the existing workflow**

If the slot is still available, the parent chatbot invokes the existing
booking workflow with the correct clinic, doctor, slot, and user
context. It then displays the booking result using the current
confirmation behavior.

**Step 9 --- Cancellation through the parent chatbot**

If the user wants to cancel, the parent chatbot follows the product's
existing process for identifying the appointment, checking that it
belongs to the user or is otherwise authorized for management, and
validating that cancellation is allowed. It then invokes the existing
cancellation workflow and displays the result.

------------------------------------------------------------------------

## 6. How the Parent Chatbot Reuses the Current Architecture

The recommended approach is to build the parent experience around the
existing appointment capabilities rather than creating an independent
booking engine.

``` mermaid
flowchart LR
    U[User] --> P[Parent Chatbot]
    P --> CD[Clinic Discovery]
    CD --> CS[Selected Clinic Context]
    CS --> DL[Clinic Doctor and Specialty Lookup]
    DL --> DS[Selected Doctor Context]
    DS --> AV[Existing Slot Availability]
    AV --> B[Existing Booking Workflow]
    P --> X[Existing Appointment Lookup / Validation]
    X --> C[Existing Cancellation Workflow]

    B --> DB[(Existing Appointment Data)]
    C --> DB
    AV --> DB
```

This is a **conceptual diagram**, not a claim about the exact current
code or database layout. The engineering team should map each box to the
real APIs, services, models, and functions already present in the
codebase.

### 6.1 Recommended responsibility split

**Parent chatbot layer** - Starts the multi-clinic conversation. - Lists
eligible clinics. - Stores the selected clinic context for the
conversation. - Shows doctors and specialties for that clinic. - Routes
the user through doctor and slot selection. - Invokes existing booking
and cancellation capabilities. - Presents clear confirmations and
error/retry messages.

**Existing clinic/appointment capabilities** - Provide clinic data and
eligibility/status information. - Return doctors associated with a
clinic. - Provide specialties and relevant doctor details. - Determine
actual slot availability. - Apply existing booking rules and create
appointments. - Apply existing cancellation rules and cancel eligible
appointments.

This division keeps the parent chatbot focused on orchestration and
discovery while existing functionality remains responsible for the
appointment operations it already handles.

### 6.2 Reuse does not mean blindly trusting chatbot state

The chatbot conversation can remember that the user selected Clinic A
and Doctor A1, but the backend must validate these relationships when an
action is performed.

For example, before booking, the backend should verify that:

1.  The clinic is valid and enabled.
2.  The selected doctor belongs to that clinic.
3.  The selected slot belongs to that doctor and is still bookable.
4.  The booking request meets the existing business rules.
5.  The booking result is returned from the authoritative booking
    workflow.

Similarly, cancellation should use the existing appointment ownership,
authorization, and eligibility checks. The chatbot must not cancel an
appointment merely because a user supplies an appointment ID.

### 6.3 Keep the two experiences consistent

Where both chatbot experiences support the same operation, they should
use the same underlying business rules. For example, if cancellation
eligibility changes in the existing booking service, the parent chatbot
should inherit that behavior by calling the same capability rather than
maintaining a separate cancellation implementation.

The parent chatbot may have a different conversation flow, but it should
not create a conflicting set of booking rules.

------------------------------------------------------------------------

## 7. Hypothetical Scenario: A User Books an Appointment

The following example is fictional and is intended to make the user
experience concrete.

### Example clinics

Suppose the platform has three registered clinics:

  -----------------------------------------------------------------------
  Clinic                  Example doctors         Example specialties
  ----------------------- ----------------------- -----------------------
  Karachi Family Clinic   Dr. Ayesha Khan;        General Physician;
                          Dr. Bilal Ahmed         Internal Medicine

  Seaview Heart Centre    Dr. Hamza Ali; Dr. Sana Cardiologist;
                          Malik                   Cardiology

  City Skin Clinic        Dr. Hira Noor;          Dermatologist;
                          Dr. Usman Raza          Dermatology
  -----------------------------------------------------------------------

These names and specialties are illustrative only. In the real system,
the chatbot should display data returned by the platform.

### Conversation example

**1. User opens the Parent Chatbot**

**Chatbot:**\
"Welcome! I can help you find a clinic, view doctors and available
appointment times, book an appointment, or manage an existing
appointment. What would you like to do?"

**User:**\
"I want to book an appointment."

**2. The chatbot displays multiple clinics**

**Chatbot:**\
"Please select a clinic."

-   Karachi Family Clinic
-   Seaview Heart Centre
-   City Skin Clinic

The list is fetched from the clinics enabled for the parent chatbot. The
user sees multiple clinics in one conversation instead of needing to
open each clinic's separate chatbot.

**User:**\
"Seaview Heart Centre."

**3. The chatbot loads doctors for the selected clinic**

The backend uses the selected clinic's ID to retrieve its doctors. It
must not mix in doctors from Karachi Family Clinic or City Skin Clinic.

**Chatbot:**\
"Here are the doctors available at Seaview Heart Centre."

-   Dr. Hamza Ali --- Cardiologist
-   Dr. Sana Malik --- Cardiology

**User:**\
"I want to book with Dr. Hamza Ali."

**4. The chatbot displays available slots for that doctor**

The chatbot requests availability for Dr. Hamza Ali in the context of
Seaview Heart Centre.

**Chatbot:**\
"Please choose an available appointment time."

-   Monday, 10:00 AM
-   Monday, 11:30 AM
-   Tuesday, 2:00 PM

These are hypothetical options. Actual dates and times must come from
the live availability source.

**User:**\
"Monday at 11:30 AM."

**5. The system validates and books the appointment**

Before booking, the backend rechecks that the selected slot is still
available. If it is available, the parent chatbot calls the existing
booking workflow. If it has already been taken, the chatbot refreshes
availability and asks the user to choose another slot.

**Chatbot --- successful booking:**\
"Your appointment has been booked successfully.

-   Clinic: Seaview Heart Centre
-   Doctor: Dr. Hamza Ali
-   Specialty: Cardiologist
-   Date: Monday
-   Time: 11:30 AM

Please keep your appointment reference for future management."

The actual confirmation should use the real appointment date, time,
reference, and other fields supported by the current product.

### What happened behind the scenes?

1.  The parent chatbot fetched the eligible clinic list.
2.  The user selected Seaview Heart Centre.
3.  The system retained the clinic ID in the conversation context.
4.  The backend fetched doctors belonging to that clinic.
5.  The user selected Dr. Hamza Ali.
6.  The backend validated that this doctor belongs to the selected
    clinic.
7.  The system fetched the doctor's available slots.
8.  The user selected a slot.
9.  The booking workflow revalidated availability and created the
    appointment.
10. The chatbot displayed the booking result.

The parent chatbot did not need to invent a new appointment-booking
engine. It coordinated the steps and reused the existing appointment
capability.

------------------------------------------------------------------------

## 8. Hypothetical Scenario: A User Cancels an Appointment

**User:**\
"I want to cancel my appointment."

**Chatbot:**\
"I can help with that. Please follow the steps to identify the
appointment you want to cancel."

The exact appointment-identification step should use the current
product's supported process---for example, authenticated appointment
history or the existing verification flow.

After identifying the appointment, the system should show enough
information for the user to recognize it, subject to privacy and
authentication rules.

**Chatbot:**\
"Is this the appointment you want to cancel?"

-   Clinic: Seaview Heart Centre
-   Doctor: Dr. Hamza Ali
-   Date and time: \[actual appointment date and time\]

**User:**\
"Yes, cancel it."

The backend checks that the user is authorized to manage the appointment
and that the appointment is eligible for cancellation. It then invokes
the existing cancellation workflow.

**Chatbot --- successful cancellation:**\
"Your appointment has been cancelled successfully."

If cancellation is not allowed, the appointment cannot be found, or
verification fails, the chatbot should explain the appropriate next step
without falsely confirming cancellation.

**Important:** The parent chatbot should not implement a weaker
cancellation process than the clinic-specific chatbot. Existing
authorization and cancellation rules should remain in force.

------------------------------------------------------------------------

## 9. Premium Clinic-Specific Chatbot Remains Available

The new parent chatbot does not remove or replace the existing
clinic-specific chatbot.

### Parent chatbot experience

A user who wants to explore clinics can start at the parent chatbot,
choose a clinic, and then book or manage an appointment.

### Clinic-specific premium experience

A clinic can continue to offer its own dedicated chatbot. A user who
enters through that clinic-specific chatbot starts directly in the
clinic's context and continues using its existing experience.

``` mermaid
flowchart TD
    U[User] --> CH{Choose chatbot experience}

    CH -->|Explore multiple clinics| P[Parent Chatbot]
    P --> PC[Select a clinic]
    PC --> PD[View that clinic's doctors]
    PD --> PB[Existing booking and cancellation capabilities]

    CH -->|Use a specific clinic's experience| S[Clinic-Specific Premium Chatbot]
    S --> SD[View that clinic's doctors]
    SD --> SB[Existing booking and cancellation capabilities]
```

Both experiences can coexist. The parent chatbot adds broader discovery,
while the clinic-specific chatbot remains a dedicated premium option.

The team should confirm the product rules that determine which clinics
are shown in the parent experience and which clinics have access to the
premium clinic-specific chatbot. Those rules should be explicit and
should not be inferred solely from the existence of a chatbot URL.

------------------------------------------------------------------------

## 10. Important Design and Validation Considerations

These are safeguards and questions for implementation planning, not
claims that the current system is missing them.

### 10.1 Clinic context must be explicit

Keep a stable clinic ID in the conversation state after the user selects
a clinic. Use this ID for doctor lookup, slot lookup, booking, and
appointment-related operations where relevant. Do not depend on a clinic
name alone.

### 10.2 Doctor-to-clinic relationship must be checked

The backend must confirm that the selected doctor belongs to the
selected clinic. This validation should happen server-side, even if the
chatbot UI only displays valid doctors.

### 10.3 Availability must be authoritative

A slot shown earlier in a conversation may no longer be available.
Revalidate availability when booking and handle conflicts by refreshing
the slot list and asking the user to choose again.

### 10.4 Preserve existing business rules

Booking, cancellation, appointment status changes, and any other
restrictions should be governed by the existing business logic. The
parent chatbot should not bypass these checks.

### 10.5 Cancellation needs appropriate verification

The chatbot should identify the appointment through the existing
supported process and verify that the user is authorized to cancel it.
An appointment ID by itself should not be treated as proof of
authorization.

### 10.6 Handle empty and error states

The parent experience should have clear responses when: - No eligible
clinics are available. - A clinic has no active doctors. - A doctor has
no available slots. - A slot becomes unavailable before booking
completes. - A booking or cancellation request fails. - A clinic is
disabled or becomes unavailable during the conversation. - The user
changes their selected clinic or doctor.

For example, if the user switches from Clinic A to Clinic B, the chatbot
must clear or replace the previous clinic's doctor and slot context. It
must not accidentally use a Clinic A doctor with Clinic B's context.

### 10.7 Privacy and data separation

Only show information the user is allowed to access. Keep
clinic-specific records correctly associated with their clinic and apply
the current authorization rules to appointment details. The parent
chatbot should not expose one clinic's private data to another clinic or
to an unauthorized user.

### 10.8 Conversation interruption and recovery

If a user leaves and returns, the product should follow an agreed rule
for restoring or restarting the conversation. Any saved state must be
revalidated before booking or cancellation; old state should not be
treated as proof that a slot is still available.

------------------------------------------------------------------------

## 11. Suggested Implementation Plan

The following is a practical sequence for engineering discussion. It
should be adjusted after the team reviews the actual codebase and APIs.

### Phase 1 --- Map existing capabilities

-   Identify the existing clinic-specific chatbot entry point and
    conversation flow.
-   Identify how clinics and doctors are retrieved.
-   Identify how doctor specialties are stored and returned.
-   Identify the current slot-availability mechanism.
-   Identify the existing booking and cancellation services or
    functions.
-   Record the existing authorization, validation, and error-handling
    behavior.

**Deliverable:** A short mapping of current components that can be
reused.

### Phase 2 --- Add parent-level clinic discovery

-   Define which clinics are eligible to appear in the parent chatbot.
-   Add or reuse a service/API that returns the eligible clinic list.
-   Display the clinic list in the parent chatbot.
-   Store and validate the selected clinic context.

**Deliverable:** Users can open the parent chatbot and select a clinic.

### Phase 3 --- Connect clinic-scoped doctor and specialty lookup

-   Fetch doctors for the selected clinic.
-   Display doctor names and specialties where available.
-   Ensure changing clinics refreshes the doctor list and clears
    dependent selections.
-   Validate the doctor-to-clinic relationship server-side.

**Deliverable:** Users can select a clinic and see the correct doctors.

### Phase 4 --- Reuse slots and booking

-   Connect doctor selection to the existing availability capability.
-   Display available slots.
-   Revalidate the selected slot during booking.
-   Invoke the existing booking workflow.
-   Return the existing booking result in a parent-chatbot-friendly
    message.

**Deliverable:** Users can book appointments through the parent chatbot.

### Phase 5 --- Reuse cancellation

-   Connect the parent chatbot to the existing
    appointment-identification and verification process.
-   Reuse cancellation eligibility and authorization checks.
-   Invoke the existing cancellation workflow.
-   Display success or a suitable failure message.

**Deliverable:** Users can manage eligible appointments through the
parent chatbot.

### Phase 6 --- Preserve the premium clinic-specific experience

-   Confirm that all existing clinic-specific chatbot entry points
    remain available.
-   Verify that premium access and clinic-level routing continue to
    work.
-   Confirm that shared appointment logic behaves consistently in both
    experiences.

**Deliverable:** Both chatbot experiences coexist without removing the
current feature.

### Phase 7 --- Test end-to-end and cross-clinic boundaries

Test at least: - Booking in Clinic A. - Booking in Clinic B. - Selecting
a doctor who belongs to the selected clinic. - Rejecting a mismatched
clinic/doctor/slot combination. - Handling a slot that becomes
unavailable. - Cancelling an eligible appointment. - Rejecting an
unauthorized cancellation. - Switching clinics mid-conversation. - A
clinic with no doctors or no available slots. - Existing clinic-specific
chatbot booking and cancellation after the parent chatbot is introduced.

**Deliverable:** Verified behavior for both the new parent experience
and the existing clinic-specific experience.

------------------------------------------------------------------------

## 12. Acceptance Criteria

The parent chatbot concept can be considered functionally complete when
the following expected behaviors have been demonstrated:

1.  A user can open one parent chatbot and see multiple eligible
    clinics.
2.  A user can select one clinic.
3.  The chatbot displays only the doctors associated with that clinic.
4.  Doctor specialties are shown when the data is available.
5.  A user can select a doctor and view that doctor's available slots.
6.  The system validates the clinic, doctor, and slot relationships on
    the backend.
7.  A user can book an appointment through the existing booking
    workflow.
8.  The system handles unavailable or conflicting slots without falsely
    confirming a booking.
9.  A user can initiate cancellation through the parent chatbot using
    the existing identification, verification, and cancellation rules.
10. The chatbot confirms booking or cancellation only after the backend
    reports success.
11. The current clinic-specific chatbot remains available as a premium
    feature.
12. The current clinic-specific chatbot continues to book and cancel
    appointments as before.
13. Switching clinics does not leave stale doctor or slot selections
    active.
14. Clinic-specific data and appointment permissions remain enforced.

------------------------------------------------------------------------

## 13. Decisions to Confirm With the Team

Before implementation, confirm these items against the existing product:

-   **Clinic eligibility:** Which registered clinics should appear in
    the parent chatbot?
-   **Clinic information:** Which fields should appear in each clinic
    option (name, location, branch, address, etc.)?
-   **Doctor information:** Which doctor fields are available today, and
    how are specialties represented?
-   **Multiple branches:** Is each branch a separate clinic record, or
    does a clinic have multiple branches?
-   **User identity:** How does the current system identify a user for
    booking and cancellation?
-   **Booking rules:** Are there existing booking limits, time windows,
    payment requirements, or confirmation steps?
-   **Cancellation rules:** What are the existing cancellation
    eligibility and verification requirements?
-   **Premium access:** How is the clinic-specific chatbot enabled and
    managed as a premium feature?
-   **Conversation state:** How long should a selected clinic or
    unfinished booking remain active?
-   **Operational behavior:** What should happen if a clinic or doctor
    becomes unavailable during an active conversation?

These questions do not change the core proposal. They ensure the parent
chatbot follows the actual platform rules rather than introducing
assumptions.

------------------------------------------------------------------------

## 14. Final Summary

The current system offers a clinic-specific chatbot experience: each
clinic has its own chatbot, doctors, slots, and existing appointment
booking/cancellation journey.

The proposal is to add a parent chatbot that brings all eligible clinics
into one shared entry point. The user opens the parent chatbot, selects
a clinic, views that clinic's doctors and specialties, chooses a doctor,
selects an available slot, and books an appointment. Cancellation is
also supported by reusing the existing cancellation capability.

**No existing feature is being removed.** The clinic-specific chatbot
remains a premium feature, while the parent chatbot adds a convenient
multi-clinic discovery experience.

The recommended architecture is to reuse existing clinic, doctor,
availability, booking, and cancellation capabilities wherever possible.
The parent chatbot should coordinate the conversation and maintain the
selected clinic context, while the backend continues to enforce the real
business rules and data relationships.

In short:

**One parent chatbot for discovering and accessing multiple clinics +
existing appointment workflows reused + clinic-specific chatbot retained
as a premium feature.**
