-- ============================================================
-- Employee Data AI Agent
-- Database Schema
-- ============================================================
CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY,
    department_code VARCHAR(20) UNIQUE NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    location VARCHAR(100),
    manager_employee_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id INTEGER PRIMARY KEY,
    employee_number VARCHAR(20) UNIQUE NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    job_title VARCHAR(150),
    department_id INTEGER NOT NULL,
    hire_date DATE,
    salary NUMERIC(12, 2),
    employment_status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_id)
        REFERENCES departments(department_id),
    CONSTRAINT chk_employee_status
        CHECK (
            employment_status IN (
                'ACTIVE',
                'INACTIVE',
                'TERMINATED',
                'ON_LEAVE'
            )
        ),
    CONSTRAINT chk_salary
        CHECK (salary IS NULL OR salary >= 0)
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_employees_department_id
    ON employees(department_id);
CREATE INDEX IF NOT EXISTS idx_employees_status
    ON employees(employment_status);
CREATE INDEX IF NOT EXISTS idx_employees_hire_date
    ON employees(hire_date);
CREATE INDEX IF NOT EXISTS idx_departments_location
    ON departments(location);
