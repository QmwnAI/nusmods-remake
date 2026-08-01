-- NUS Study Planner schema
-- All tables use TEXT primary keys for IDs that come from Clerk; everything else uses INTEGER PRIMARY KEY AUTOINCREMENT.
-- Run via: python seed.py  (which calls db.init_db())

PRAGMA foreign_keys = ON;

-- ====== Users ======
-- Mirrors Clerk's user table; we don't store passwords here.
-- contact_telegram is an optional handle the user may share for study-group
-- contact (Feature 11). Stored without the @ prefix; the frontend displays
-- it as @handle. Empty / NULL means "don't surface a Telegram contact".
CREATE TABLE IF NOT EXISTS users (
  id                TEXT    PRIMARY KEY,           -- Clerk user_id, or 'dev-user-*' in dev
  email             TEXT    NOT NULL,
  display_name      TEXT,
  major_code        TEXT,                          -- e.g. 'CS', 'BZA'
  matric_year       INTEGER,
  contact_telegram  TEXT,                          -- optional study-group contact (no @)
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ====== Modules ======
-- Synced from NUSMods. prereq_tree stores the raw NUSMods structure as JSON.
CREATE TABLE IF NOT EXISTS modules (
  code           TEXT    PRIMARY KEY,
  title          TEXT    NOT NULL,
  description    TEXT,
  mcs            REAL    NOT NULL,            -- some modules are 2.5, 1.5 credits
  department     TEXT,
  faculty        TEXT,
  prereq_tree    TEXT,                        -- JSON: {"and":[...]}, {"or":[...]}, or "CS1101S"
  prereq_string  TEXT,                        -- human-readable, from NUSMods
  preclusion     TEXT,                        -- free-text: modules that conflict with this one
  corequisite    TEXT,                        -- free-text: modules to take simultaneously
  workload       TEXT,                        -- JSON array [lec, tut, lab, project, prep]
  semester_data  TEXT,                        -- JSON: full semesterData from NUSMods (sem, examDate, timetable)
  acad_year      TEXT,
  updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_modules_dept ON modules(department);

-- ====== Majors ======
-- Catalog of degree programs offered. The set of (major_code) values here must
-- match the major_code column in degree_requirements; we don't enforce a FK
-- because requirements may be seeded before majors during bootstrap.
CREATE TABLE IF NOT EXISTS majors (
  code         TEXT    PRIMARY KEY,            -- short code, e.g. 'CS', 'BZA', 'IS'
  name         TEXT    NOT NULL,               -- full name, e.g. 'Bachelor of Computing (Computer Science)'
  faculty      TEXT,                           -- 'School of Computing', etc. (used to group in onboarding)
  total_mcs    INTEGER NOT NULL,               -- usually 160 for a 4-year BSc; mirrors sum of requirement MCs
  acad_year    TEXT,
  display_order INTEGER DEFAULT 0
);

-- ====== Degree requirements ======
-- One row per (major, category) bucket. e.g. (CS, FOUNDATION, 24 MC).
CREATE TABLE IF NOT EXISTS degree_requirements (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  major_code     TEXT    NOT NULL,
  category       TEXT    NOT NULL,             -- machine key: FOUNDATION, CS_BREADTH, ...
  label          TEXT    NOT NULL,             -- display: "CS Foundation"
  required_mcs   INTEGER NOT NULL,
  acad_year      TEXT,
  display_order  INTEGER DEFAULT 0,
  UNIQUE(major_code, category, acad_year)
);

-- Which modules count toward which requirement.
-- A module can satisfy multiple requirements (rare but possible).
CREATE TABLE IF NOT EXISTS requirement_modules (
  requirement_id  INTEGER NOT NULL,
  module_code     TEXT    NOT NULL,
  is_compulsory   INTEGER DEFAULT 0,
  PRIMARY KEY (requirement_id, module_code),
  FOREIGN KEY (requirement_id) REFERENCES degree_requirements(id) ON DELETE CASCADE,
  FOREIGN KEY (module_code) REFERENCES modules(code) ON DELETE CASCADE
);

-- ====== Study plans ======
CREATE TABLE IF NOT EXISTS study_plans (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      TEXT    NOT NULL,
  name         TEXT    NOT NULL DEFAULT 'My Plan',
  is_active    INTEGER DEFAULT 1,
  created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_plans_user ON study_plans(user_id);

-- ====== Plan entries ======
-- One row per module placed in a semester. The (plan_id, module_code) uniqueness
-- means a module can only appear once in a given plan; moving it = UPDATE.
CREATE TABLE IF NOT EXISTS plan_entries (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id       INTEGER NOT NULL,
  module_code   TEXT    NOT NULL,
  semester_id   TEXT    NOT NULL,                -- 'Y1S1' .. 'Y4S2'
  position      INTEGER DEFAULT 0,               -- ordering within semester
  grade         TEXT,                            -- 'A+', ..., 'F'. NULL = not graded yet.
  is_su         INTEGER DEFAULT 0,
  is_completed  INTEGER DEFAULT 0,
  notes         TEXT,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (plan_id) REFERENCES study_plans(id) ON DELETE CASCADE,
  FOREIGN KEY (module_code) REFERENCES modules(code),
  UNIQUE(plan_id, module_code)
);

CREATE INDEX IF NOT EXISTS idx_entries_plan ON plan_entries(plan_id);
CREATE INDEX IF NOT EXISTS idx_entries_sem  ON plan_entries(plan_id, semester_id);

-- ====== Feature 5: Plan sharing ======
-- Each row = one share grant. The sharer (plan owner) decides whether grades
-- are visible to the recipient via include_grades; default 0 (modules-only).
-- Note: this table doesn't permit shared_with_user_id to be NULL — sharing
-- with someone who hasn't signed up yet would need a different mechanism
-- (e.g. a pending_invites table keyed by email). Today the UI requires the
-- recipient to exist by the time the share is created.
CREATE TABLE IF NOT EXISTS plan_shares (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id                INTEGER NOT NULL,
  shared_with_user_id    TEXT    NOT NULL,
  include_grades         INTEGER NOT NULL DEFAULT 0,
  created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (plan_id) REFERENCES study_plans(id) ON DELETE CASCADE,
  FOREIGN KEY (shared_with_user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE(plan_id, shared_with_user_id)
);
CREATE INDEX IF NOT EXISTS idx_plan_shares_user ON plan_shares(shared_with_user_id);

-- ====== Feature 6: Study group opt-ins ======
CREATE TABLE IF NOT EXISTS study_group_optins (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       TEXT    NOT NULL,
  module_code   TEXT    NOT NULL,
  semester_id   TEXT    NOT NULL,
  message       TEXT,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (module_code) REFERENCES modules(code),
  UNIQUE(user_id, module_code, semester_id)
);

CREATE INDEX IF NOT EXISTS idx_optins_module ON study_group_optins(module_code, semester_id);

-- ====== Feature 7: Badges ======
-- Badges are mostly computed on the fly, but we store earned timestamps for the celebration moment.
CREATE TABLE IF NOT EXISTS earned_badges (
  user_id     TEXT NOT NULL,
  badge_key   TEXT NOT NULL,
  earned_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, badge_key),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
