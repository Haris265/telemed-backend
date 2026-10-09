"""Fatimiyah Hospital consultant schedule (October 2026 PDF).

Weekdays: Mon=0 … Sun=6.
Only Dr. entries; On Leave / On Call / non-doctor staff omitted.
Times are 24h HH:MM strings.
"""

from __future__ import annotations

MON, TUE, WED, THU, FRI, SAT, SUN = range(7)

MON_FRI = [MON, TUE, WED, THU, FRI]
MON_SAT = [MON, TUE, WED, THU, FRI, SAT]
MON_WED_FRI = [MON, WED, FRI]
TUE_THU_SAT = [TUE, THU, SAT]
TUE_THU = [TUE, THU]
MON_THU = [MON, THU]
WED_FRI = [WED, FRI]
TUE_FRI = [TUE, FRI]
MON_FRI_SUN = [MON, TUE, WED, THU, FRI, SUN]

# Each entry: speciality, first_name, last_name, windows[{weekdays, start, end}]
# Same person may appear more than once with different specialities; the seed
# command merges by normalized name.
SCHEDULE: list[dict] = [
    # --- Internal Medicine ---
    {
        "speciality": "Internal Medicine",
        "first_name": "Pyar",
        "last_name": "Ali",
        "windows": [{"weekdays": MON_FRI, "start": "12:00", "end": "14:00"}],
    },
    {
        "speciality": "Internal Medicine",
        "first_name": "Arjan",
        "last_name": "Kumar",
        "windows": [
            {"weekdays": TUE_THU_SAT, "start": "16:00", "end": "18:00"},
            {"weekdays": WED_FRI, "start": "20:00", "end": "21:30"},
        ],
    },
    {
        "speciality": "Internal Medicine",
        "first_name": "Tahira",
        "last_name": "Naqvi",
        "windows": [
            {"weekdays": [MON, TUE, THU, SAT], "start": "14:00", "end": "16:00"}
        ],
    },
    {
        "speciality": "Internal Medicine",
        "first_name": "Huda",
        "last_name": "Naim",
        "windows": [
            {"weekdays": [MON, WED, THU, FRI], "start": "18:00", "end": "20:00"}
        ],
    },
    # --- Chest ---
    {
        "speciality": "Chest Specialist",
        "first_name": "Syed Ali",
        "last_name": "Abbas",
        "windows": [{"weekdays": MON_WED_FRI, "start": "16:00", "end": "17:00"}],
    },
    {
        "speciality": "Chest Specialist",
        "first_name": "Muhammad",
        "last_name": "Umair",
        "windows": [{"weekdays": MON_FRI, "start": "17:00", "end": "18:00"}],
    },
    {
        "speciality": "Chest Specialist",
        "first_name": "Ashfaque",
        "last_name": "Ahmed",
        "windows": [
            {"weekdays": MON_WED_FRI, "start": "18:00", "end": "19:00"},
            {"weekdays": TUE_THU, "start": "18:00", "end": "20:00"},
            {"weekdays": [SAT], "start": "20:00", "end": "21:00"},
        ],
    },
    # --- Cardiology ---
    {
        "speciality": "Cardiology",
        "first_name": "Syed Hasnain",
        "last_name": "Mujtaba",
        "windows": [{"weekdays": MON_SAT, "start": "15:00", "end": "18:00"}],
    },
    {
        "speciality": "Cardiology",
        "first_name": "Mubashir",
        "last_name": "Hussain",
        "windows": [{"weekdays": TUE_THU_SAT, "start": "18:30", "end": "20:30"}],
    },
    {
        "speciality": "Cardiology",
        "first_name": "Zair",
        "last_name": "Hussain",
        "windows": [{"weekdays": [MON, WED, SAT], "start": "12:00", "end": "13:00"}],
    },
    {
        "speciality": "Paediatric Cardiology",
        "first_name": "Amber",
        "last_name": "Kamran",
        "windows": [{"weekdays": [MON, WED], "start": "14:00", "end": "15:30"}],
    },
    # --- Child Specialists ---
    {
        "speciality": "Child Specialist",
        "first_name": "Insiyah",
        "last_name": "Agha",
        "windows": [{"weekdays": TUE_THU, "start": "11:00", "end": "12:00"}],
    },
    {
        "speciality": "Child Specialist",
        "first_name": "Amin",
        "last_name": "Ali",
        "windows": [{"weekdays": MON_WED_FRI, "start": "20:00", "end": "21:00"}],
    },
    {
        "speciality": "Child Specialist",
        "first_name": "Sohail",
        "last_name": "Sundrani",
        "windows": [{"weekdays": TUE_THU, "start": "16:30", "end": "17:30"}],
    },
    {
        "speciality": "Child Specialist",
        "first_name": "Samar",
        "last_name": "Hassan",
        "windows": [{"weekdays": MON_SAT, "start": "11:30", "end": "13:30"}],
    },
    {
        "speciality": "Child Specialist",
        "first_name": "Hasnain",
        "last_name": "Lokhandwala",
        "windows": [{"weekdays": MON_WED_FRI, "start": "17:00", "end": "19:00"}],
    },
    {
        "speciality": "Child Specialist",
        "first_name": "Mohd",
        "last_name": "Hanif",
        "windows": [{"weekdays": MON_WED_FRI, "start": "16:30", "end": "17:30"}],
    },
    {
        "speciality": "Child Specialist",
        "first_name": "Gulab",
        "last_name": "Rai",
        "windows": [{"weekdays": TUE_THU_SAT, "start": "19:00", "end": "21:00"}],
    },
    # --- Paediatric Surgeons ---
    {
        "speciality": "Paediatric Surgery",
        "first_name": "S. Mohd Raees",
        "last_name": "Hussain",
        "windows": [{"weekdays": TUE_THU, "start": "15:00", "end": "16:00"}],
    },
    {
        "speciality": "Paediatric Surgery",
        "first_name": "Fatima",
        "last_name": "Majid",
        "windows": [
            {"weekdays": [MON], "start": "14:00", "end": "15:00"},
            {"weekdays": [THU], "start": "16:00", "end": "17:00"},
        ],
    },
    # --- Family Physicians ---
    {
        "speciality": "Family Medicine",
        "first_name": "Syed Rais",
        "last_name": "Haider",
        "windows": [{"weekdays": MON_SAT, "start": "10:00", "end": "16:00"}],
    },
    {
        "speciality": "Family Medicine",
        "first_name": "Kamal",
        "last_name": "Ahmed",
        "windows": [{"weekdays": MON_FRI_SUN, "start": "17:00", "end": "23:00"}],
    },
    {
        "speciality": "Family Medicine",
        "first_name": "Syed Ahmed Zamin",
        "last_name": "Rizvi",
        "windows": [{"weekdays": MON_SAT, "start": "23:00", "end": "05:00"}],
    },
    # --- Diabetologist / Endocrinologists ---
    {
        "speciality": "Endocrinology",
        "first_name": "Ali",
        "last_name": "Asghar",
        "windows": [{"weekdays": [TUE, SAT], "start": "17:30", "end": "19:00"}],
    },
    {
        "speciality": "Endocrinology",
        "first_name": "Asad",
        "last_name": "Abbas",
        "windows": [
            {"weekdays": [MON, FRI], "start": "19:00", "end": "20:00"},
            {"weekdays": [WED], "start": "18:00", "end": "20:00"},
            {"weekdays": [THU], "start": "20:00", "end": "21:00"},
            {"weekdays": [TUE, SAT], "start": "10:30", "end": "11:30"},
        ],
    },
    {
        "speciality": "Endocrinology",
        "first_name": "Sabiha",
        "last_name": "Bano",
        "windows": [
            {"weekdays": [TUE, THU, FRI], "start": "18:30", "end": "20:00"}
        ],
    },
    # --- Gynaecologists ---
    {
        "speciality": "Gynaecology",
        "first_name": "Farah",
        "last_name": "Naz",
        "windows": [{"weekdays": [WED], "start": "10:30", "end": "12:00"}],
    },
    {
        "speciality": "Gynaecology",
        "first_name": "Syeda Rahila",
        "last_name": "Mohsin",
        "windows": [{"weekdays": [WED], "start": "14:00", "end": "15:00"}],
    },
    {
        "speciality": "Gynaecology",
        "first_name": "Shahida",
        "last_name": "Abbas",
        "windows": [{"weekdays": [MON, FRI], "start": "15:00", "end": "18:00"}],
    },
    {
        "speciality": "Gynaecology",
        "first_name": "Tahira",
        "last_name": "Shah",
        "windows": [
            {"weekdays": [WED, THU], "start": "15:00", "end": "17:00"},
            {"weekdays": [SAT], "start": "17:00", "end": "19:00"},
        ],
    },
    {
        "speciality": "Gynaecology",
        "first_name": "Kaneez",
        "last_name": "Fatima",
        "windows": [{"weekdays": MON_SAT, "start": "10:00", "end": "13:00"}],
    },
    {
        "speciality": "Gynaecology",
        "first_name": "Zeba",
        "last_name": "Abbas",
        "windows": [
            {"weekdays": [MON, TUE, FRI], "start": "16:00", "end": "19:30"},
            {"weekdays": [SAT], "start": "10:00", "end": "12:00"},
        ],
    },
    # --- General Surgeons ---
    {
        "speciality": "General Surgery",
        "first_name": "Mohd",
        "last_name": "Tayyab",
        "windows": [
            {"weekdays": [MON, THU, SAT], "start": "16:00", "end": "20:00"}
        ],
    },
    {
        "speciality": "General Surgery",
        "first_name": "Asad Ali",
        "last_name": "Kerawala",
        "windows": [
            {"weekdays": [MON, THU, SAT], "start": "15:00", "end": "16:00"}
        ],
    },
    {
        "speciality": "General Surgery",
        "first_name": "Atia",
        "last_name": "Hussain",
        "windows": [{"weekdays": MON_FRI, "start": "11:30", "end": "12:30"}],
    },
    {
        "speciality": "General Surgery",
        "first_name": "Hina",
        "last_name": "Khan",
        "windows": [
            {"weekdays": [TUE, WED, FRI], "start": "16:00", "end": "17:00"}
        ],
    },
    {
        "speciality": "General Surgery",
        "first_name": "Zia",
        "last_name": "Ul-Islam",
        "windows": [{"weekdays": TUE_THU_SAT, "start": "12:00", "end": "13:00"}],
    },
    # --- Orthopaedic ---
    {
        "speciality": "Orthopaedics",
        "first_name": "Ghulam Abbas",
        "last_name": "Jaffri",
        "windows": [{"weekdays": MON_SAT, "start": "10:00", "end": "16:00"}],
    },
    {
        "speciality": "Orthopaedics",
        "first_name": "Mehtab Ahmed",
        "last_name": "Pirwani",
        "windows": [{"weekdays": MON_FRI, "start": "12:00", "end": "13:00"}],
    },
    {
        "speciality": "Orthopaedics",
        "first_name": "Ghazanfar Ali",
        "last_name": "Shah",
        "windows": [{"weekdays": MON_WED_FRI, "start": "16:30", "end": "18:00"}],
    },
    {
        "speciality": "Orthopaedics",
        "first_name": "Muhammad Kazim",
        "last_name": "Rahim",
        "windows": [{"weekdays": [TUE, SAT], "start": "19:00", "end": "21:00"}],
    },
    {
        "speciality": "Orthopaedics",
        "first_name": "Syed Muhammad",
        "last_name": "Sibtain",
        "windows": [{"weekdays": MON_THU, "start": "16:30", "end": "17:30"}],
    },
    {
        "speciality": "Orthopaedics",
        "first_name": "Mohd Farhan",
        "last_name": "Sozera",
        "windows": [
            {"weekdays": [TUE, SAT], "start": "16:30", "end": "18:00"},
            {"weekdays": [THU], "start": "18:00", "end": "20:00"},
        ],
    },
    {
        "speciality": "Orthopaedics",
        "first_name": "Rehan",
        "last_name": "Ali",
        "windows": [
            {"weekdays": [THU], "start": "14:30", "end": "15:30"},
            {"weekdays": [SAT], "start": "15:00", "end": "16:00"},
        ],
    },
    # --- Gastroenterology ---
    {
        "speciality": "Gastroenterology",
        "first_name": "Kanwal",
        "last_name": "Butani",
        "windows": [
            {"weekdays": MON_WED_FRI, "start": "17:00", "end": "18:00"},
            {"weekdays": TUE_THU_SAT, "start": "20:30", "end": "21:30"},
        ],
    },
    {
        "speciality": "Gastroenterology",
        "first_name": "Ghulamullah",
        "last_name": "Lail",
        "windows": [{"weekdays": TUE_THU_SAT, "start": "14:30", "end": "15:30"}],
    },
    {
        "speciality": "Gastroenterology",
        "first_name": "Tanveer",
        "last_name": "Khalid",
        "windows": [{"weekdays": MON_WED_FRI, "start": "18:00", "end": "19:00"}],
    },
    {
        "speciality": "Gastroenterology",
        "first_name": "Farheen",
        "last_name": "Taufiq",
        "windows": [
            {"weekdays": [MON, WED], "start": "15:00", "end": "16:00"},
            {"weekdays": [SAT], "start": "19:00", "end": "20:00"},
        ],
    },
    # Dr. Imran Khan — On Leave (skipped)
    # --- Psychiatrists ---
    {
        "speciality": "Psychiatry",
        "first_name": "Syed Zafar",
        "last_name": "Haider",
        "windows": [{"weekdays": [SAT], "start": "10:00", "end": "14:00"}],
    },
    {
        "speciality": "Psychiatry",
        "first_name": "Mohd",
        "last_name": "Ilyas",
        "windows": [{"weekdays": TUE_THU, "start": "19:00", "end": "20:00"}],
    },
    {
        "speciality": "Psychiatry",
        "first_name": "Tooba",
        "last_name": "Anum",
        "windows": [{"weekdays": TUE_FRI, "start": "15:00", "end": "17:00"}],
    },
    # --- Neuro Physician ---
    {
        "speciality": "Neurology",
        "first_name": "Teerth",
        "last_name": "Das",
        "windows": [{"weekdays": MON_FRI, "start": "14:30", "end": "15:30"}],
    },
    {
        "speciality": "Neurology",
        "first_name": "Sanjay",
        "last_name": "Kumar",
        "windows": [{"weekdays": TUE_THU_SAT, "start": "19:30", "end": "21:00"}],
    },
    # --- Neuro Surgeons ---
    {
        "speciality": "Neurosurgery",
        "first_name": "Ghulam Mohd",
        "last_name": "Brohi",
        "windows": [{"weekdays": [TUE, WED], "start": "19:00", "end": "20:30"}],
    },
    {
        "speciality": "Neurosurgery",
        "first_name": "Zeeshan",
        "last_name": "Mughal",
        "windows": [{"weekdays": TUE_FRI, "start": "16:30", "end": "17:30"}],
    },
    # Dr. Syed Mohd Hussain — On Leave (skipped)
    # --- Nephrologists ---
    {
        "speciality": "Nephrology",
        "first_name": "Ali Mohsin",
        "last_name": "Raza",
        "windows": [
            {"weekdays": [MON, WED, SAT], "start": "16:00", "end": "18:00"},
            {"weekdays": [THU], "start": "18:00", "end": "19:00"},
        ],
    },
    {
        "speciality": "Nephrology",
        "first_name": "Mehdi Husain",
        "last_name": "Nayani",
        "windows": [{"weekdays": [TUE], "start": "13:00", "end": "14:00"}],
    },
    # --- Oncologist ---
    {
        "speciality": "Oncology",
        "first_name": "Furrukh",
        "last_name": "Ashraf",
        "windows": [{"weekdays": MON_THU, "start": "14:00", "end": "15:00"}],
    },
    # --- Clinical Hematology ---
    {
        "speciality": "Clinical Hematology",
        "first_name": "Anjly",
        "last_name": "Aujha",
        "windows": [{"weekdays": WED_FRI, "start": "18:30", "end": "20:30"}],
    },
    # --- Skin ---
    {
        "speciality": "Dermatology",
        "first_name": "Jawed Ahmed",
        "last_name": "Memon",
        "windows": [
            {"weekdays": [MON, TUE, THU, SAT], "start": "18:30", "end": "19:30"}
        ],
    },
    {
        "speciality": "Dermatology",
        "first_name": "Aqsa Asghar",
        "last_name": "Ali",
        "windows": [{"weekdays": MON_WED_FRI, "start": "16:00", "end": "17:30"}],
    },
    {
        "speciality": "Dermatology",
        "first_name": "Kanwal",
        "last_name": "Kaukab",
        "windows": [
            {"weekdays": MON_WED_FRI, "start": "12:00", "end": "15:00"},
            {"weekdays": TUE_THU_SAT, "start": "12:00", "end": "17:00"},
        ],
    },
    # --- Eye ---
    {
        "speciality": "Ophthalmology",
        "first_name": "Maqbool",
        "last_name": "Hussain",
        "windows": [{"weekdays": [WED], "start": "20:00", "end": "21:00"}],
    },
    {
        "speciality": "Ophthalmology",
        "first_name": "Narain",
        "last_name": "Das",
        "windows": [
            {"weekdays": MON_THU, "start": "17:00", "end": "18:30"},
            {"weekdays": [SAT], "start": "17:30", "end": "19:00"},
        ],
    },
    {
        "speciality": "Ophthalmology",
        "first_name": "Mohd Asghar",
        "last_name": "Rajani",
        "windows": [
            {"weekdays": WED_FRI, "start": "16:00", "end": "18:00"},
            {"weekdays": [THU, SAT], "start": "16:00", "end": "17:00"},
        ],
    },
    {
        "speciality": "Ophthalmology",
        "first_name": "Tahira",
        "last_name": "Zulfiqar",
        "windows": [
            {"weekdays": [MON, WED, THU], "start": "10:30", "end": "12:30"}
        ],
    },
    # --- Plastic Surgeons (Atia Hussain also under General Surgery — merged) ---
    {
        "speciality": "Plastic Surgery",
        "first_name": "Atia",
        "last_name": "Hussain",
        "windows": [{"weekdays": MON_FRI, "start": "11:30", "end": "12:30"}],
    },
    {
        "speciality": "Plastic Surgery",
        "first_name": "Erum",
        "last_name": "Naz",
        "windows": [{"weekdays": MON_THU, "start": "16:00", "end": "17:00"}],
    },
    # --- ENT ---
    {
        "speciality": "ENT",
        "first_name": "Anis A.",
        "last_name": "Allana",
        "windows": [{"weekdays": MON_SAT, "start": "11:30", "end": "13:30"}],
    },
    {
        "speciality": "ENT",
        "first_name": "Shahid Raza",
        "last_name": "Syed",
        "windows": [{"weekdays": MON_SAT, "start": "10:00", "end": "11:30"}],
    },
    {
        "speciality": "ENT",
        "first_name": "Maisam",
        "last_name": "Abbas",
        "windows": [{"weekdays": [TUE], "start": "16:00", "end": "17:30"}],
    },
    # Dr. Maheen Pyar Ali — On Leave (skipped)
    {
        "speciality": "ENT",
        "first_name": "Syeda Amna",
        "last_name": "Bukhari",
        "windows": [
            {"weekdays": [FRI], "start": "16:00", "end": "17:00"},
            {"weekdays": [SAT], "start": "18:00", "end": "19:00"},
        ],
    },
    # --- Urologists ---
    {
        "speciality": "Urology",
        "first_name": "Sunil",
        "last_name": "Kumar",
        "windows": [
            {"weekdays": [MON, TUE, THU, FRI], "start": "15:00", "end": "16:00"}
        ],
    },
    {
        "speciality": "Urology",
        "first_name": "Ali",
        "last_name": "Raza",
        "windows": [
            {"weekdays": [MON], "start": "21:00", "end": "22:00"},
            {"weekdays": WED_FRI, "start": "17:30", "end": "19:00"},
        ],
    },
    {
        "speciality": "Urology",
        "first_name": "Yasir",
        "last_name": "Murtaza",
        "windows": [
            {"weekdays": [WED], "start": "16:00", "end": "17:00"},
            {"weekdays": [SAT], "start": "18:00", "end": "19:00"},
        ],
    },
    # --- Dentists ---
    {
        "speciality": "Dentist",
        "first_name": "Mahwish",
        "last_name": "Zehra",
        "windows": [{"weekdays": MON_SAT, "start": "10:00", "end": "13:00"}],
    },
    {
        "speciality": "Dentist",
        "first_name": "Urooj",
        "last_name": "Fatima",
        "windows": [{"weekdays": MON_SAT, "start": "09:00", "end": "15:00"}],
    },
    {
        "speciality": "Dentist",
        "first_name": "Fatima",
        "last_name": "Raza",
        "windows": [{"weekdays": MON_SAT, "start": "15:00", "end": "17:00"}],
    },
    {
        "speciality": "Dentist",
        "first_name": "Muhammad",
        "last_name": "Shayan",
        "windows": [{"weekdays": MON_SAT, "start": "17:00", "end": "22:00"}],
    },
    # --- Facio-Maxillary ---
    {
        "speciality": "Facio-Maxillary Surgery",
        "first_name": "Zia",
        "last_name": "Abbas",
        "windows": [{"weekdays": [THU], "start": "14:00", "end": "16:00"}],
    },
    {
        "speciality": "Facio-Maxillary Surgery",
        "first_name": "Raza",
        "last_name": "Ali",
        "windows": [{"weekdays": [FRI], "start": "16:00", "end": "17:30"}],
    },
    {
        "speciality": "Facio-Maxillary Surgery",
        "first_name": "Abdullah",
        "last_name": "Salman",
        "windows": [{"weekdays": [WED], "start": "18:00", "end": "19:00"}],
    },
    # Dr. Maria Shabbir — On Call (skipped)
    # --- Ultrasound / Radiologist Sonologists ---
    {
        "speciality": "Radiology",
        "first_name": "Hassan",
        "last_name": "Abbas",
        "windows": [{"weekdays": MON_SAT, "start": "15:00", "end": "16:00"}],
    },
    {
        "speciality": "Radiology",
        "first_name": "Ghulam",
        "last_name": "Abbas",
        "windows": [
            {"weekdays": [MON, TUE, WED, THU, SAT], "start": "10:00", "end": "13:00"},
            {"weekdays": [FRI], "start": "10:00", "end": "12:00"},
            {"weekdays": MON_SAT, "start": "18:00", "end": "19:30"},
        ],
    },
    {
        "speciality": "Radiology",
        "first_name": "Atia",
        "last_name": "Fareen",
        "windows": [{"weekdays": TUE_THU_SAT, "start": "17:30", "end": "20:30"}],
    },
    {
        "speciality": "Radiology",
        "first_name": "Zakia",
        "last_name": "Baloch",
        "windows": [
            {"weekdays": [TUE, WED, THU], "start": "09:00", "end": "11:00"}
        ],
    },
    {
        "speciality": "Radiology",
        "first_name": "Zahida",
        "last_name": "Parveen",
        "windows": [{"weekdays": MON_WED_FRI, "start": "17:00", "end": "19:30"}],
    },
    {
        "speciality": "Radiology",
        "first_name": "Nasrin",
        "last_name": "Haque",
        "windows": [
            {"weekdays": [TUE, WED, THU], "start": "11:00", "end": "13:30"}
        ],
    },
    {
        "speciality": "Radiology",
        "first_name": "Shama",
        "last_name": "Zehra",
        "windows": [
            {"weekdays": [MON, FRI, SAT], "start": "09:30", "end": "13:30"}
        ],
    },
    {
        "speciality": "Radiology",
        "first_name": "Uzma Raza",
        "last_name": "Maheen",
        "windows": [
            {"weekdays": MON_SAT, "start": "14:00", "end": "16:30"},
            {"weekdays": MON_SAT, "start": "22:00", "end": "00:00"},
        ],
    },
    # --- CT / Scan ---
    {
        "speciality": "Radiology",
        "first_name": "Kailash",
        "last_name": "Kailash",
        "windows": [{"weekdays": MON_SAT, "start": "16:00", "end": "19:00"}],
    },
    # --- Anaesthesia ---
    {
        "speciality": "Anaesthesia",
        "first_name": "Sibte Arif",
        "last_name": "Naqvi",
        "windows": [{"weekdays": MON_SAT, "start": "12:00", "end": "13:00"}],
    },
]
