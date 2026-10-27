# Telemed — System Feature Checklist

QA / product tracking checklist for the full PatientCare ecosystem.  
All items start unchecked — tick as you verify.

**Surfaces**

| # | Surface | Channel | Primary role |
|---|---------|---------|--------------|
| 1 | Superadmin panel | Web (`/superadmin`) | Platform billing & clinics |
| 2 | Clinic Admin panel | Web (`/clinic`) | Clinic ops, doctors, ledger |
| 3 | Hospital / Ops Admin | Web (`/admin`) | Catalog, doctors, patients, appointments |
| 4 | Patient app | Mobile (Expo) | Booking, queue, reports |
| 5 | Doctor app | Mobile (Expo) | Queue, SOAP, Rx, clinics |
| 6 | WhatsApp + Assistant | Meta WA / playground | Frictionless booking & FAQ |

Frontend apps live under sibling repo `telemed/` (`admin/`, `mobile/`, `doctor-mobile/`). APIs live in this backend.

---

## 1. Superadmin panel

Login: `/superadmin/login` · Shell: `/superadmin/*`

### Dashboard (`/superadmin/dashboard`)
- [ ] KPI: active clinic subscriptions
- [ ] KPI: pending subscription requests
- [ ] KPI: active packages
- [ ] KPI: cash collected this month
- [ ] Quick links to clinics / requests / packages / payments

### Packages (`/superadmin/packages`)
- [ ] List subscription packages
- [ ] Create package
- [ ] Edit / update package
- [ ] Activate / deactivate package

### Clinics (`/superadmin/clinics`)
- [ ] List clinics
- [ ] Create clinic (name, city, area, admin credentials, etc.)
- [ ] Create clinic **without** latitude / longitude
- [ ] Soft-delete / deactivate clinic
- [ ] View clinic detail / billing link context

### Requests (`/superadmin/requests`)
- [ ] List pending package / subscription requests
- [ ] Approve request
- [ ] Reject request
- [ ] Direct-assign package to a clinic

### Invoices (`/superadmin/invoices`)
- [ ] List platform invoices across clinics
- [ ] Filter / open invoice detail (if UI supports)

### Payments (`/superadmin/payments`)
- [ ] List recorded payments
- [ ] See amount / clinic / date context

### Ledger (`/superadmin/ledger`)
- [ ] View platform ledger entries
- [ ] Trace invoice ↔ payment activity

---

## 2. Clinic Admin panel

Login: `/clinic/login` · Shell: `/clinic/*`  
Doctors / appointments nav may be gated until subscription is active.

### Dashboard (`/clinic/dashboard`)
- [ ] Show clinic summary KPIs (doctors, appointments, packages, amount due)
- [ ] Lock / unlock doctors & appointments when subscription inactive
- [ ] Navigate to invoices / packages / subscription

### Doctors (`/clinic/doctors`)
- [ ] List doctors linked to this clinic
- [ ] Open doctor detail (`/clinic/doctors/[id]`)

#### Doctor detail
- [ ] Profile / speciality summary
- [ ] Consultation fee display & edit
- [ ] Commission type (percentage / fixed) & value edit
- [ ] Live fee split preview (clinic vs doctor share) on fee/% change
- [ ] Save → PATCH fee/commission and refresh totals
- [ ] Weekly / date schedule (availability)
- [ ] Linked patients list for this clinic
- [ ] Appointments list for this doctor at this clinic

### Appointments (`/clinic/appointments`)
- [ ] List clinic-scoped appointments
- [ ] Filter by status / date (if UI supports)
- [ ] Open appointment detail (`/clinic/appointments/[id]`)

### Packages (`/clinic/packages`)
- [ ] Browse available packages / offers
- [ ] Request a package / subscription

### Invoices (`/clinic/invoices`)
- [ ] List clinic invoices
- [ ] See due / paid status

### Subscription (`/clinic/subscription`)
- [ ] View current subscription status
- [ ] See package details / expiry / lock state

### Payments & Ledger (`/clinic/ledger`)
- [ ] View clinic payments
- [ ] View clinic ledger entries

---

## 3. Hospital / Ops Admin panel

Login: `/login` · Shell: `/admin/*`

### Dashboard (`/admin/dashboard`)
- [ ] Total doctors KPI
- [ ] Total patients KPI
- [ ] Total appointments KPI
- [ ] Links into doctors / patients / appointments

### Specialities (`/admin/specialities`)
- [ ] List specialities
- [ ] Create speciality
- [ ] Edit / update speciality
- [ ] Soft-delete / deactivate (if supported)

### Clinics (`/admin/clinics`)
- [ ] List clinics (ops catalog view)
- [ ] Create / edit clinic (ops fields)

### Doctors (`/admin/doctors`)
- [ ] Doctor directory / search
- [ ] Doctor onboarding (`/admin/doctors/onboarding`) — create account + profile
- [ ] Doctor detail (`/admin/doctors/[id]`)
- [ ] Assign clinics / specialities / availability (as exposed in UI)

### Subscriptions (`/admin/subscriptions`)
- [ ] View doctor / clinic subscription listings (ops)
- [ ] Manage subscription rows as exposed in UI

### Marketing (`/admin/marketing-subscriptions`)
- [ ] List marketing subscription products / plans
- [ ] Manage marketing subscription entries

### Patients (`/admin/patients`)
- [ ] Patient list / search
- [ ] Patient detail (`/admin/patients/[id]`)
- [ ] View linked appointments / history on detail

### Appointments (`/admin/appointments`)
- [ ] Appointment list / filters
- [ ] Create appointment (if UI supports)
- [ ] Appointment detail (`/admin/appointments/[id]`)
- [ ] Update status / notes as exposed in UI

---

## 4. Patient mobile app

Expo app: `telemed/mobile`

### Auth
- [ ] Request OTP (`/login`)
- [ ] Verify OTP (`/login/otp`)
- [ ] Name onboarding for new patients (`/login/name`)
- [ ] Persist session / auto-redirect when logged in
- [ ] Logout from profile

### Home (`(tabs)/index`)
- [ ] Home summary / next appointment cards
- [ ] Shortcuts into book / queue / reports

### Book (`(tabs)/book` + nested routes)
- [ ] Browse specialities
- [ ] Doctors by speciality (`/book/speciality/[id]`)
- [ ] Doctor booking flow (`/book/[doctorUuid]`) — clinic, date, slot
- [ ] Confirm & create appointment
- [ ] Appointment detail (`/appointment/[id]`)
- [ ] “Book on WhatsApp” deep link (when clinic WA number configured)

### Clinics
- [ ] Nearby clinics (`/clinics/nearby`) using location
- [ ] Clinic detail (`/clinics/[id]`)
- [ ] Clinic speciality → doctors (`/clinics/[id]/speciality/[specId]`)

### Reports (`(tabs)/reports`)
- [ ] List past visits / reports
- [ ] Open history index (`/history`) and detail (`/history/[id]`)
- [ ] View prescription / clinical summary when available

### Live Queue (`(tabs)/queue`)
- [ ] Live token / queue for active appointment
- [ ] Token lookup (guest / code) via API-backed flow
- [ ] Wait-time / current vs patient token display

### Profile (`(tabs)/profile`)
- [ ] View patient profile (`/api/patient/me`)
- [ ] Update profile fields if UI allows
- [ ] Logout

### Symptom check (`/symptoms`)
- [ ] Submit symptoms
- [ ] Receive suggested speciality / guidance from API

---

## 5. Doctor mobile app

Expo app: `telemed/doctor-mobile`  
Login with admin-created doctor email/password.

### Auth
- [ ] Email / password login (`/login`)
- [ ] Session persist + redirect
- [ ] Logout from profile
- [ ] Change password (API: `/api/auth/change-password/`) if exposed in UI

### Home (`(tabs)/index`)
- [ ] Today’s queue / dashboard analytics
- [ ] Start / advance live clinic tokens
- [ ] Quick open appointment cards

### Appointments (`(tabs)/appointments`)
- [ ] Tabs or filters: today / future / completed / rejected
- [ ] Open appointment detail (`/appointment/[id]`)
- [ ] Complete appointment
- [ ] Reject / no-show appointment
- [ ] Skip handling updates live queue

### Clinical notes & prescription (appointment detail)
- [ ] View / edit SOAP / clinical notes
- [ ] View / edit prescription (medicines, advice)
- [ ] Save clinical + Rx
- [ ] Optional WhatsApp send of Rx on complete (when doctor WA connected)

### Patients (`(tabs)/patients`)
- [ ] Patient list for this doctor
- [ ] Patient detail (`/patient/[uuid]`)
- [ ] Visit history / last prescription

### Clinics (`(tabs)/clinics`)
- [ ] List linked clinics
- [ ] Clinic detail (`/clinic/[id]`)
- [ ] Manage weekly availability per clinic
- [ ] Replace / delete availability slots

### Profile (`(tabs)/profile`)
- [ ] View doctor profile (`/api/doctor/me`)
- [ ] Account settings / logout

### Doctor WhatsApp (API-backed; UI may be partial)
- [ ] WhatsApp connection status
- [ ] Connect (OAuth / session)
- [ ] Connect manual
- [ ] Disconnect
- [ ] Embedded signup page (`/api/whatsapp/embedded-signup/`)

---

## 6. WhatsApp patient bot + Assistant

Backend: `whatsapp/`, `assistant/`

### Patient bot — onboarding & menu
- [ ] New phone creates WhatsApp session
- [ ] Collect patient name
- [ ] OTP verification when required
- [ ] Main menu text (book / appointments / FAQ)
- [ ] Reply `menu` / `cancel` returns home

### Patient bot — booking
- [ ] Choose booking mode (marketplace vs bound doctor, where applicable)
- [ ] Select speciality
- [ ] Select doctor (or search by name)
- [ ] Select clinic
- [ ] Select date (open booking horizon)
- [ ] Select time slot
- [ ] Confirm booking → token issued
- [ ] Payment choice: bank transfer vs cash at clinic
- [ ] Payment slip upload + OCR verify (when bank path)
- [ ] View my upcoming appointments (menu option 2)

### Patient bot — FAQ
- [ ] Ask a question (menu option 0)
- [ ] Context-aware FAQ answer (doctor / clinic / booking horizon)
- [ ] Fallback guidance to book via option 1

### Meta / ops plumbing
- [ ] Webhook verify (`GET /api/whatsapp/webhook/`)
- [ ] Inbound messages (`POST /api/whatsapp/webhook/`)
- [ ] Local simulate endpoint (`POST /api/whatsapp/simulate/`) without Meta credentials

### Clinic Assistant playground
- [ ] Playground page (`/api/assistant/playground/`)
- [ ] Chat turn (`/api/assistant/chat/`)
- [ ] Reset conversation (`/api/assistant/reset/`)

---

## Cross-cutting (optional QA)

- [ ] Role-based login routing (superadmin / clinic admin / hospital admin / doctor / patient)
- [ ] JWT access + refresh tokens
- [ ] Subscription lock blocks clinic doctors & appointments until paid/active
- [ ] Media uploads (slips, Rx assets) served from `/media/`
- [ ] Seed commands (e.g. Fatimiyah schedule / demo appointments) for demo clinics

---

*Generated from current routes, sidebars, and app tabs. Update this file when new surfaces ship.*
